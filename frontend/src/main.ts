import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import VueKonva from 'vue-konva'

// Import Tailwind CSS
import './style.css'
import { logger } from '@/utils/logger' 

logger.log('Vue app starting...')
logger.log('Environment:', import.meta.env.MODE)
logger.log('API URL:', import.meta.env.VITE_API_URL)

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(VueKonva)

logger.log('Mounting Vue app...')
app.mount('#app')
logger.log('Vue app mounted!')
