<template>
  <div id="app">
    <router-view />
    <Toaster />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import { Toaster } from 'vue-sonner'
import 'vue-sonner/style.css'

const authStore = useAuthStore()

onMounted(() => {
  authStore.checkAuth()
})
</script>

<style>
#app {
  min-height: 100vh;
}
</style>
