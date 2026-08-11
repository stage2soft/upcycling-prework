import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import './styles.css'
import App from './App.vue'

const vuetify = createVuetify({
  theme: {
    defaultTheme: 'prework',
    themes: { prework: { dark: false, colors: { primary: '#2563eb', secondary: '#0891b2', surface: '#ffffff', background: '#f4f7fb', error: '#dc2626', success: '#059669' } } },
  },
})

createApp(App).use(vuetify).mount('#app')
