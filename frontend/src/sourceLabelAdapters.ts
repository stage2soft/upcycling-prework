export type Point = { x: number; y: number }
export type OverlayObject = { id: string; title: string; points: Point[]; bbox: [number, number, number, number]; properties: unknown; raw: unknown }
export type ParsedOverlay = {
  width?: number; height?: number; objects: OverlayObject[]; adapter: string; error?: string
  coordinateSystem?: 'image' | 'world_xy'; viewBox?: [number, number, number, number]
  worldObjects?: OverlayObject[]; projectionNote?: string
}

const number = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : undefined
const pointsFrom = (value: unknown): Point[] => {
  const found: Point[] = []
  const visit = (item: unknown) => {
    if (Array.isArray(item)) item.forEach(visit)
    else if (item && typeof item === 'object') {
      const row = item as Record<string, unknown>; const x = number(row.x); const y = number(row.y)
      if (x !== undefined && y !== undefined) found.push({ x, y })
    }
  }
  visit(value); return found
}
const bounds = (points: Point[]): [number, number, number, number] => {
  const xs = points.map(p => p.x), ys = points.map(p => p.y)
  const x = Math.min(...xs), y = Math.min(...ys)
  return [x, y, Math.max(...xs) - x, Math.max(...ys) - y]
}
const cuboidYaw = (annotation: any) => {
  const quaternion = annotation?.rotation_quaternion
  const qx = number(quaternion?.x) ?? 0, qy = number(quaternion?.y) ?? 0
  const qz = number(quaternion?.z) ?? 0, qw = number(quaternion?.w) ?? 1
  return Math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))
}
const cuboidPoints = (annotation: any): Point[] | null => {
  const position = annotation?.position, size = annotation?.size, quaternion = annotation?.rotation_quaternion
  const cx = number(position?.x), cy = number(position?.y), width = number(size?.x), height = number(size?.y)
  if (cx === undefined || cy === undefined || width === undefined || height === undefined || width <= 0 || height <= 0) return null
  const yaw = cuboidYaw(annotation)
  const cosine = Math.cos(yaw), sine = Math.sin(yaw)
  return [[-width / 2, -height / 2], [width / 2, -height / 2], [width / 2, height / 2], [-width / 2, height / 2]].map(([x, y]) => ({
    x: cx + x * cosine - y * sine,
    y: -(cy + x * sine + y * cosine),
  }))
}
const projectCuboid = (annotation: any, imageWidth: number, imageHeight: number, horizontalFov = 90): Point[] | null => {
  const position = annotation?.position, size = annotation?.size
  const cx = number(position?.x), cy = number(position?.y), cz = number(position?.z)
  const sx = number(size?.x), sy = number(size?.y), sz = number(size?.z)
  if ([cx, cy, cz, sx, sy, sz].some(value => value === undefined) || sx! <= 0 || sy! <= 0 || sz! <= 0) return null
  const yaw = cuboidYaw(annotation), cosine = Math.cos(yaw), sine = Math.sin(yaw)
  const focalLength = imageWidth / (2 * Math.tan(horizontalFov * Math.PI / 360))
  const projected: Point[] = []
  for (const localX of [-sx! / 2, sx! / 2]) for (const localY of [-sy! / 2, sy! / 2]) for (const localZ of [-sz! / 2, sz! / 2]) {
    const x = cx! + localX * cosine - localY * sine
    const depth = cy! + localX * sine + localY * cosine
    const z = cz! + localZ
    if (depth <= .05) continue
    projected.push({ x: imageWidth / 2 + focalLength * x / depth, y: imageHeight / 2 - focalLength * z / depth })
  }
  if (projected.length < 4) return null
  const [x, y, width, height] = bounds(projected)
  const left = Math.max(0, x), top = Math.max(0, y)
  const right = Math.min(imageWidth, x + width), bottom = Math.min(imageHeight, y + height)
  if (right <= left || bottom <= top) return null
  return [{ x: left, y: top }, { x: right, y: top }, { x: right, y: bottom }, { x: left, y: bottom }]
}
const worldViewBox = (objects: OverlayObject[]): [number, number, number, number] => {
  const points = objects.flatMap(item => item.points), xs = points.map(point => point.x), ys = points.map(point => point.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const width = Math.max(maxX - minX, 1), height = Math.max(maxY - minY, 1)
  const padding = Math.max(width, height) * .08
  return [minX - padding, minY - padding, width + padding * 2, height + padding * 2]
}

export function parseLabel(value: unknown, imageSize?: { width: number; height: number }): ParsedOverlay {
  if (!value || typeof value !== 'object') return { objects: [], adapter: 'none', error: '라벨 JSON이 객체 형식이 아닙니다.' }
  const root = value as Record<string, any>
  const size = root.meta?.size || root.image || {}
  const width = number(size.width), height = number(size.height)
  const projectionWidth = imageSize?.width || width
  const projectionHeight = imageSize?.height || height
  if (Array.isArray(root.objects)) {
    const worldCuboids = root.objects.flatMap((item: any, index: number) => {
      const points = cuboidPoints(item?.annotation)
      return !points ? [] : [{
        id: `cuboid-${index}`, title: item.class_name || item.label || `객체 ${index + 1}`,
        points, bbox: bounds(points), properties: { annotation: item.annotation, properties: item.properties }, raw: item,
      }]
    })
    if (worldCuboids.length && projectionWidth && projectionHeight) {
      const imageCuboids = root.objects.flatMap((item: any, index: number) => {
        const points = projectCuboid(item?.annotation, projectionWidth, projectionHeight)
        return !points ? [] : [{
          id: `cuboid-${index}`, title: item.class_name || item.label || `객체 ${index + 1}`,
          points, bbox: bounds(points), properties: { annotation: item.annotation, properties: item.properties }, raw: item,
        }]
      })
      if (imageCuboids.length) return {
        width: projectionWidth, height: projectionHeight, objects: imageCuboids, adapter: 'objects.annotation.3d_cuboid.pinhole', coordinateSystem: 'image',
        worldObjects: worldCuboids, viewBox: worldViewBox(worldCuboids),
        projectionNote: '원천 이미지 실제 해상도와 x=좌우, y=깊이, z=높이 및 수평 FOV 90°를 가정했습니다.',
      }
    }
    if (worldCuboids.length) return {
      objects: worldCuboids, adapter: 'objects.annotation.3d_cuboid', coordinateSystem: 'world_xy', viewBox: worldViewBox(worldCuboids),
      worldObjects: worldCuboids,
    }
    const polygons = root.objects.flatMap((item: any, index: number) => {
      const points = Array.isArray(item?.annotation) ? pointsFrom(item.annotation) : []
      return points.length < 2 ? [] : [{ id: `polygon-${index}`, title: item.class_name || item.label || `객체 ${index + 1}`, points, bbox: bounds(points), properties: item.properties, raw: item }]
    })
    if (polygons.length) return { width, height, objects: polygons, adapter: 'objects.annotation', coordinateSystem: 'image' }
    const boxes = root.objects.flatMap((item: any, index: number) => {
      const box = item?.bbox
      if (!Array.isArray(box) || box.length < 4 || box.slice(0, 4).some((v: unknown) => number(v) === undefined)) return []
      const [x, y, w, h] = box.map(Number); const points = [{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }]
      return [{ id: `bbox-${index}`, title: item.class_name || item.label || `객체 ${index + 1}`, points, bbox: [x, y, w, h] as [number, number, number, number], properties: item.properties, raw: item }]
    })
    if (boxes.length) return { width, height, objects: boxes, adapter: 'objects.bbox', coordinateSystem: 'image' }
  }
  if (Array.isArray(root.annotations)) {
    const objects = root.annotations.flatMap((item: any, index: number) => {
      if (!Array.isArray(item?.bbox) || item.bbox.length < 4) return []
      const [x, y, w, h] = item.bbox.map(Number); if (![x, y, w, h].every(Number.isFinite)) return []
      const points = [{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }]
      return [{ id: `coco-${index}`, title: item.category_name || `Category ${item.category_id ?? index + 1}`, points, bbox: [x, y, w, h] as [number, number, number, number], properties: item.attributes, raw: item }]
    })
    if (objects.length) return { width, height, objects, adapter: 'coco.annotations', coordinateSystem: 'image' }
  }
  return { width, height, objects: [], adapter: 'unsupported', error: '지원하는 polygon 또는 bbox 형식을 찾지 못했습니다.' }
}
