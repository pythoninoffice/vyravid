import { onMounted, onBeforeUnmount, nextTick, type Ref } from 'vue'
import interact from 'interactjs'

export interface TimelineInteractOptions {
  clipSelector: string
  pixelsPerSecond: Ref<number>
  onDragMove?: (clipId: string | number, newStartTime: number) => void
  onDragEnd?: (clipId: string | number, finalStartTime: number) => void
  onResizeMove?: (clipId: string | number, newDuration: number, newStartTime: number) => void
  onResizeEnd?: (clipId: string | number, finalDuration: number, finalStartTime: number) => void
  dragRestriction?: 'parent' | { left: number; right: number; top: number; bottom: number }
  snapToGrid?: boolean
  gridSize?: number
}

export function useTimelineInteract(options: TimelineInteractOptions) {
  const {
    clipSelector,
    pixelsPerSecond,
    onDragMove,
    onDragEnd,
    onResizeMove,
    onResizeEnd,
    dragRestriction = 'parent',
    snapToGrid = false,
    gridSize = 10
  } = options

  const setupInteract = () => {
    // Unset any existing interactions first to prevent duplicates
    interact(clipSelector).unset()

    // Setup draggable
    interact(clipSelector)
      .draggable({
        modifiers: [
          ...(dragRestriction ? [
            interact.modifiers.restrict({
              restriction: dragRestriction,
              elementRect: { left: 0, right: 1, top: 0, bottom: 1 }
            })
          ] : []),
          ...(snapToGrid ? [
            interact.modifiers.snap({
              targets: [
                interact.snappers.grid({ x: gridSize, y: 0 })
              ],
              range: Infinity,
              relativePoints: [{ x: 0, y: 0 }]
            })
          ] : [])
        ],
        lockAxis: 'x',
        ignoreFrom: '.resize-handle, .delete-btn', // Don't start drag from resize handles or delete button
        listeners: {
          start(event) {
            const target = event.target
            // Initialize cumulative offset tracking
            target.setAttribute('data-x', '0')
            target.setAttribute('data-dragging', 'true')
          },
          move(event) {
            const target = event.target
            const clipId = target.dataset.clipId

            if (!clipId) return

            // Track cumulative offset using data-x attribute
            const x = (parseFloat(target.getAttribute('data-x')) || 0) + event.dx

            // Use transform for smooth visual feedback during drag
            target.style.transform = `translateX(${x}px)`
            target.setAttribute('data-x', x.toString())

            // Calculate new start time for callback (optional, for live updates)
            if (onDragMove) {
              const originalLeft = parseFloat(target.style.left || '0')
              const newLeft = originalLeft + x
              const newStartTime = Math.max(0, newLeft / pixelsPerSecond.value)
              onDragMove(clipId, newStartTime)
            }
          },
          end(event) {
            const target = event.target
            const clipId = target.dataset.clipId

            if (!clipId) return

            // Calculate final position
            const x = parseFloat(target.getAttribute('data-x')) || 0
            const originalLeft = parseFloat(target.style.left || '0')
            const finalLeft = originalLeft + x
            const finalStartTime = Math.max(0, finalLeft / pixelsPerSecond.value)

            // Call the end callback which will update the data model
            // The data model update will trigger a re-render with the new position
            if (onDragEnd) {
              onDragEnd(clipId, finalStartTime)
            }

            // Wait for Vue to re-render with the new position before removing transform
            // This prevents the jiggling effect
            nextTick(() => {
              target.style.transform = ''
              target.setAttribute('data-x', '0')
              target.removeAttribute('data-dragging')
            })
          }
        }
      })
      .resizable({
        edges: { left: '.resize-left', right: '.resize-right' },
        modifiers: [
          interact.modifiers.restrictSize({
            min: { width: 20, height: 0 }
          }),
          ...(snapToGrid ? [
            interact.modifiers.snapSize({
              targets: [
                interact.snappers.grid({ x: gridSize, y: 0 })
              ]
            })
          ] : [])
        ],
        listeners: {
          start(event) {
            const target = event.target
            // Initialize resize tracking attributes
            target.setAttribute('data-resize-x', '0')
            target.setAttribute('data-resize-width', target.style.width || '0')
            target.setAttribute('data-resizing', 'true')
          },
          move(event) {
            const target = event.target
            const clipId = target.dataset.clipId

            if (!clipId) return

            // Get original dimensions
            const originalLeft = parseFloat(target.style.left || '0')
            const originalWidth = parseFloat(target.getAttribute('data-resize-width') || target.style.width || '0')
            let x = parseFloat(target.getAttribute('data-resize-x')) || 0

            let newStartTime = originalLeft / pixelsPerSecond.value
            let newWidth = originalWidth

            // Handle left edge resize (affects both position and width)
            if (event.edges.left) {
              x += event.deltaRect.left
              const newLeft = Math.max(0, originalLeft + x)
              newStartTime = newLeft / pixelsPerSecond.value
              newWidth = originalWidth - x

              // Use transform for visual feedback during resize
              target.style.transform = `translateX(${x}px)`
              target.setAttribute('data-resize-x', x.toString())
            }

            // Handle right edge resize (only affects width)
            if (event.edges.right) {
              newWidth = event.rect.width
            }

            // Update visual width
            target.style.width = `${newWidth}px`

            // Convert to duration
            const newDuration = Math.max(0.1, newWidth / pixelsPerSecond.value)

            // Callback for live updates
            if (onResizeMove) {
              onResizeMove(clipId, newDuration, newStartTime)
            }
          },
          end(event) {
            const target = event.target
            const clipId = target.dataset.clipId

            if (!clipId) return

            // Calculate final dimensions
            const originalLeft = parseFloat(target.style.left || '0')
            const x = parseFloat(target.getAttribute('data-resize-x')) || 0
            const finalLeft = event.edges.left ? Math.max(0, originalLeft + x) : originalLeft
            const finalWidth = parseFloat(target.style.width || '0')

            const finalStartTime = finalLeft / pixelsPerSecond.value
            const finalDuration = Math.max(0.1, finalWidth / pixelsPerSecond.value)

            // Call the end callback which will update the data model
            if (onResizeEnd) {
              onResizeEnd(clipId, finalDuration, finalStartTime)
            }

            // Wait for Vue to re-render with the new dimensions before removing transform
            // This prevents the jiggling effect
            nextTick(() => {
              target.style.transform = ''
              target.setAttribute('data-resize-x', '0')
              target.removeAttribute('data-resize-width')
              target.removeAttribute('data-resizing')
            })
          }
        }
      })
  }

  const cleanupInteract = () => {
    interact(clipSelector).unset()
  }

  onMounted(() => {
    setupInteract()
  })

  onBeforeUnmount(() => {
    cleanupInteract()
  })

  return {
    setupInteract,
    cleanupInteract
  }
}
