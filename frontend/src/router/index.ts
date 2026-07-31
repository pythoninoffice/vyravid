import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const DashboardView = () => import('@/views/DashboardView.vue')
const SimpleProjectCreator = () => import('@/views/SimpleProjectCreator.vue')
const ProjectManager = () => import('@/components/ProjectManager.vue')

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    {
      path: '/',
      redirect: '/app',
    },
    {
      path: '/app',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'dashboard',
          component: DashboardView,
        },
        {
          path: 'projects',
          name: 'projects',
          component: ProjectManager,
        },
        {
          path: 'projects/:id',
          name: 'project-details',
          component: SimpleProjectCreator,
        },
        {
          path: 'simple-creator/:id?',
          name: 'simple-creator',
          component: SimpleProjectCreator,
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/app',
    },
  ],
})

// No auth guards — local tool is always open
router.beforeEach((_to, _from, next) => next())

export default router
