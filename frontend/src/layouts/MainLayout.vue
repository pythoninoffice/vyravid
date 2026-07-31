<template>
  <div class="layout-container">
    <header v-if="!isSimpleCreatorRoute" class="md:hidden mobile-header">
      <div class="header-content">
        <button @click="toggleLeftDrawer" class="menu-button" aria-label="Toggle navigation menu">
          <span class="material-icons text-black">menu</span>
        </button>
        <div class="w-8"></div>
      </div>
    </header>

    <div class="main-container bg-gray-50">
      <AppSidebar
        v-if="!isSimpleCreatorRoute"
        :is-open="leftDrawerOpen"
        user-email="local@openvid.local"
        @create-new-video="createNewVideo"
        @logout="() => {}"
        @toggle="toggleLeftDrawer"
        class="sidebar-hidden-mobile"
      />

      <div
        v-if="leftDrawerOpen && windowWidth < 768 && !isSimpleCreatorRoute"
        class="sidebar-backdrop"
        @click="toggleLeftDrawer"
      ></div>

      <main
        :class="[
          'main-content',
          isSimpleCreatorRoute
            ? 'main-no-sidebar'
            : leftDrawerOpen
              ? 'main-with-sidebar'
              : 'main-full-width',
        ]"
      >
        <router-view :key="routerViewKey" class="flex flex-col w-full h-full" />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppSidebar from '@/components/AppSidebar.vue'
import apiClient from '@/api/apiClient'
import { toast } from 'vue-sonner'

const router = useRouter()
const route = useRoute()

const routerViewKey = computed(() => route.fullPath)
const isSimpleCreatorRoute = computed(() => route.path.includes('/simple-creator'))
const isProjectDetailRoute = computed(() => /^\/app\/projects\/[^/]+$/.test(route.path))

const leftDrawerOpen = ref(true)
const windowWidth = ref(window.innerWidth)

watch(
  isProjectDetailRoute,
  (isDetail) => {
    leftDrawerOpen.value = !isDetail
  },
  { immediate: true }
)

function checkScreenSize() {
  windowWidth.value = window.innerWidth
}

function toggleLeftDrawer() {
  leftDrawerOpen.value = !leftDrawerOpen.value
}

async function createNewVideo() {
  try {
    const response = await apiClient.post('/api/projects/draft', {
      title: 'Untitled Project',
      draftData: {
        editableContent: '',
        lastSavedAt: new Date().toISOString(),
        currentLanguage: 'en',
        scenes: [],
      },
    })
    const projectId = response.data?.projectId || response.data?.project_id || response.data?.id
    if (projectId) {
      router.push(`/app/projects/${projectId}`)
    } else {
      router.push('/app/simple-creator')
    }
  } catch (e: any) {
    console.error(e)
    toast.error('Failed to create project')
    router.push('/app/simple-creator')
  }
}

onMounted(() => {
  window.addEventListener('resize', checkScreenSize)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkScreenSize)
})
</script>

<style scoped>
.layout-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.main-container {
  display: flex;
  flex: 1;
  min-height: 100vh;
}
.main-content {
  flex: 1;
  min-width: 0;
  transition: margin-left 0.2s ease;
}
.main-with-sidebar {
  margin-left: 0;
}
.main-full-width,
.main-no-sidebar {
  margin-left: 0;
  width: 100%;
}
.mobile-header {
  display: none;
}
.sidebar-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 40;
}
@media (max-width: 767px) {
  .mobile-header {
    display: block;
    padding: 0.75rem 1rem;
    background: white;
    border-bottom: 1px solid #e5e7eb;
  }
  .header-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .menu-button {
    padding: 0.5rem;
  }
}
</style>
