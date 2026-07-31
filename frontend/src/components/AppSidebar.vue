<template>
  <aside :class="['sidebar overflow-hidden', isOpen ? 'sidebar-open' : 'sidebar-closed']">
    <div class="sidebar-container overflow-hidden">
      <div class="sidebar-top">
        <div v-if="isOpen" class="flex items-end px-3 py-3">
          <a href="/app" class="pb-1 font-bold text-lg text-gray-900 tracking-tight">Vyravid</a>
          <button
            @click="$emit('toggle')"
            class="toggle-btn p-1.5 rounded hover:bg-gray-100 ml-auto"
            title="Collapse sidebar"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              stroke-width="2" class="w-5 h-5">
              <rect width="18" height="18" x="3" y="3" rx="2"></rect>
              <path d="M9 3v18"></path>
            </svg>
          </button>
        </div>
        <div v-else class="flex flex-col items-center px-2 py-3">
          <button @click="$emit('toggle')" class="toggle-btn p-1.5 rounded hover:bg-gray-100" title="Expand sidebar">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              stroke-width="2" class="w-5 h-5 rotate-180">
              <rect width="18" height="18" x="3" y="3" rx="2"></rect>
              <path d="M9 3v18"></path>
            </svg>
          </button>
        </div>
      </div>

      <div class="flex flex-col gap-1 px-3 mb-2">
        <div
          @click="$emit('create-new-video')"
          class="flex items-center px-3 py-2 bg-orange-400 hover:bg-orange-500 text-white rounded-lg text-sm font-medium cursor-pointer transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2"
            stroke="currentColor" :class="isOpen ? 'size-5 mr-2' : 'size-5 ml-1'">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          <span v-if="isOpen">New Video</span>
        </div>
      </div>

      <div class="sidebar-middle">
        <div class="sidebar-section">
          <router-link to="/app" class="nav-link" exact-active-class="router-link-active" :exact="true">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
              stroke="currentColor" :class="isOpen ? 'size-5 mr-2' : 'size-5'">
              <path stroke-linecap="round" stroke-linejoin="round"
                d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
            </svg>
            <span v-if="isOpen">Dashboard</span>
          </router-link>

          <router-link to="/app/projects" class="nav-link">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
              stroke="currentColor" :class="isOpen ? 'size-5 mr-2' : 'size-5'">
              <path stroke-linecap="round" stroke-linejoin="round"
                d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
            </svg>
            <span v-if="isOpen">My Projects</span>
          </router-link>
        </div>
      </div>

      <div class="flex-shrink-0 pt-2 mt-auto flex flex-col gap-1 overflow-hidden px-3 pb-4">
        <div v-if="isOpen" class="text-xs text-gray-400 px-2">
          Local mode · no account needed
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{
  isOpen: boolean
  userEmail?: string
}>()

defineEmits<{
  toggle: []
  'create-new-video': []
  logout: []
}>()
</script>

<style scoped>
.sidebar {
  height: 100vh;
  position: sticky;
  top: 0;
  background: white;
  border-right: 1px solid #e5e7eb;
  transition: width 0.2s ease;
  z-index: 50;
  display: flex;
  flex-direction: column;
}
.sidebar-open {
  width: 240px;
}
.sidebar-closed {
  width: 64px;
}
.sidebar-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.sidebar-middle {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 0;
}
.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0 0.5rem;
}
.nav-link {
  display: flex;
  align-items: center;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
  text-decoration: none;
  transition: background 0.15s;
}
.nav-link:hover {
  background: #f3f4f6;
}
.nav-link.router-link-active {
  background: #fff7ed;
  color: #ea580c;
}
@media (max-width: 767px) {
  .sidebar {
    position: fixed;
    left: 0;
    transform: translateX(-100%);
  }
  .sidebar-open {
    transform: translateX(0);
  }
}
</style>
