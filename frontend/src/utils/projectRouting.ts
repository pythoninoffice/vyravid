interface RoutableProject {
  id: string
  creationStep?: string
  projectType?: string
}

export const isTikTokSlideshowProject = (project: RoutableProject): boolean =>
  project.projectType === 'tiktok_slideshow' || project.creationStep === 'slideshow'

export const getProjectEditorRoute = (project: RoutableProject) => {
  if (isTikTokSlideshowProject(project)) {
    return {
      path: '/app/tiktok-slideshow',
      query: { projectId: project.id }
    }
  }

  return `/app/projects/${project.id}`
}
