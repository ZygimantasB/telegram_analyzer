import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

// Import components
import { ThemeToggle } from './components/ThemeToggle'
import { Navbar } from './components/Navbar'
import { Card, CardHeader, CardContent, CardFooter } from './components/Card'
import { Button } from './components/Button'
import { Badge } from './components/Badge'
import { Avatar } from './components/Avatar'

// Component registry for mounting
const components: Record<string, React.ComponentType<any>> = {
  ThemeToggle,
  Navbar,
  Card,
  CardHeader,
  CardContent,
  CardFooter,
  Button,
  Badge,
  Avatar,
}

// Mount components to DOM elements with data-react-component attribute
function mountComponents() {
  const elements = document.querySelectorAll('[data-react-component]')

  elements.forEach((element) => {
    const componentName = element.getAttribute('data-react-component')
    if (!componentName) return

    const Component = components[componentName]
    if (!Component) {
      console.warn(`Component "${componentName}" not found in registry`)
      return
    }

    // Parse props from data-react-props attribute
    let props = {}
    const propsAttr = element.getAttribute('data-react-props')
    if (propsAttr) {
      try {
        props = JSON.parse(propsAttr)
      } catch (e) {
        console.error(`Failed to parse props for ${componentName}:`, e)
      }
    }

    // Get inner HTML as children if present
    const innerHTML = element.innerHTML.trim()
    if (innerHTML && !props.children) {
      props = { ...props, dangerouslySetInnerHTML: { __html: innerHTML } }
    }

    // Clear the element and mount React component
    element.innerHTML = ''

    const root = createRoot(element)
    root.render(
      <StrictMode>
        <Component {...props} />
      </StrictMode>
    )
  })
}

// Expose components globally for direct use
declare global {
  interface Window {
    TelegramAnalyzer: {
      components: typeof components
      mountComponents: typeof mountComponents
      createRoot: typeof createRoot
    }
  }
}

window.TelegramAnalyzer = {
  components,
  mountComponents,
  createRoot,
}

// Auto-mount on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mountComponents)
} else {
  mountComponents()
}

// Export for module usage
export { components, mountComponents }
