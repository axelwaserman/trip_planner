import { createSystem, defaultConfig, defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    tokens: {
      colors: {
        bg: {
          canvas: { value: 'oklch(98.5% 0.005 95)' },
          surface: { value: 'oklch(100% 0 0)' },
        },
        fg: {
          primary: { value: 'oklch(18% 0.01 270)' },
          secondary: { value: 'oklch(48% 0.01 270)' },
          muted: { value: 'oklch(65% 0.005 270)' },
        },
        border: {
          subtle: { value: 'oklch(92% 0.005 95)' },
          strong: { value: 'oklch(80% 0.005 95)' },
        },
        accent: {
          solid: { value: 'oklch(48% 0.13 245)' },
          muted: { value: 'oklch(95% 0.02 245)' },
        },
        danger: {
          solid: { value: 'oklch(55% 0.18 25)' },
          muted: { value: 'oklch(96% 0.02 25)' },
        },
      },
      fonts: {
        display: { value: "'Fraunces', serif" },
        body: { value: "'Inter', sans-serif" },
      },
      radii: {
        sm: { value: '4px' },
        md: { value: '6px' },
        lg: { value: '8px' },
        full: { value: '9999px' },
      },
    },
  },
})

export const system = createSystem(defaultConfig, config)
