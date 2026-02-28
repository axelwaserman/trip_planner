# Chakra UI Theming Reference

Advanced theming patterns for Chakra UI v3 with TypeScript.

## Theme Configuration

### Creating a Custom System

```tsx
// theme.ts
import { createSystem, defaultConfig, defineConfig } from '@chakra-ui/react'
import type { SystemConfig } from '@chakra-ui/react'

const config = defineConfig({
  // Prefix CSS variables
  cssVarsPrefix: 'app',

  // Enforce token usage (errors if non-token values used)
  strictTokens: true,

  theme: {
    tokens: {
      // Base tokens
    },
    semanticTokens: {
      // Semantic aliases with light/dark support
    },
    recipes: {
      // Single-part component variants
    },
    slotRecipes: {
      // Multi-part component variants
    },
  },
})

export const system = createSystem(defaultConfig, config)

// Type export for use in components
export type AppSystem = typeof system
```

### Token Types

```tsx
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    tokens: {
      // Colors - use value: string format
      colors: {
        brand: {
          50: { value: '#e6f2ff' },
          100: { value: '#b3d9ff' },
          200: { value: '#80bfff' },
          300: { value: '#4da6ff' },
          400: { value: '#1a8cff' },
          500: { value: '#0073e6' },
          600: { value: '#005cb3' },
          700: { value: '#004480' },
          800: { value: '#002d4d' },
          900: { value: '#00161a' },
          950: { value: '#000d10' },
        },
      },

      // Spacing
      spacing: {
        xs: { value: '0.25rem' },
        sm: { value: '0.5rem' },
        md: { value: '1rem' },
        lg: { value: '1.5rem' },
        xl: { value: '2rem' },
        '2xl': { value: '3rem' },
        '3xl': { value: '4rem' },
      },

      // Font sizes
      fontSizes: {
        xs: { value: '0.75rem' },
        sm: { value: '0.875rem' },
        md: { value: '1rem' },
        lg: { value: '1.125rem' },
        xl: { value: '1.25rem' },
        '2xl': { value: '1.5rem' },
        '3xl': { value: '1.875rem' },
        '4xl': { value: '2.25rem' },
        '5xl': { value: '3rem' },
      },

      // Font weights
      fontWeights: {
        normal: { value: '400' },
        medium: { value: '500' },
        semibold: { value: '600' },
        bold: { value: '700' },
      },

      // Line heights
      lineHeights: {
        none: { value: '1' },
        tight: { value: '1.25' },
        snug: { value: '1.375' },
        normal: { value: '1.5' },
        relaxed: { value: '1.625' },
        loose: { value: '2' },
      },

      // Border radius
      radii: {
        none: { value: '0' },
        sm: { value: '0.125rem' },
        md: { value: '0.375rem' },
        lg: { value: '0.5rem' },
        xl: { value: '0.75rem' },
        '2xl': { value: '1rem' },
        '3xl': { value: '1.5rem' },
        full: { value: '9999px' },
      },

      // Shadows
      shadows: {
        xs: { value: '0 1px 2px rgba(0, 0, 0, 0.05)' },
        sm: { value: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)' },
        md: { value: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)' },
        lg: { value: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)' },
        xl: { value: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)' },
        '2xl': { value: '0 25px 50px -12px rgba(0, 0, 0, 0.25)' },
        inner: { value: 'inset 0 2px 4px rgba(0, 0, 0, 0.06)' },
      },

      // Z-index scale
      zIndex: {
        hide: { value: -1 },
        base: { value: 0 },
        docked: { value: 10 },
        dropdown: { value: 1000 },
        sticky: { value: 1100 },
        banner: { value: 1200 },
        overlay: { value: 1300 },
        modal: { value: 1400 },
        popover: { value: 1500 },
        skipLink: { value: 1600 },
        toast: { value: 1700 },
        tooltip: { value: 1800 },
      },

      // Animation durations
      durations: {
        fastest: { value: '50ms' },
        faster: { value: '100ms' },
        fast: { value: '150ms' },
        normal: { value: '200ms' },
        slow: { value: '300ms' },
        slower: { value: '400ms' },
        slowest: { value: '500ms' },
      },

      // Animation easings
      easings: {
        default: { value: 'cubic-bezier(0.4, 0, 0.2, 1)' },
        linear: { value: 'linear' },
        in: { value: 'cubic-bezier(0.4, 0, 1, 1)' },
        out: { value: 'cubic-bezier(0, 0, 0.2, 1)' },
        inOut: { value: 'cubic-bezier(0.4, 0, 0.2, 1)' },
      },

      // Borders
      borders: {
        none: { value: 'none' },
        default: { value: '1px solid' },
        thick: { value: '2px solid' },
      },

      // Assets (images, icons as data URIs)
      assets: {
        logo: { value: 'url(/logo.svg)' },
        checkmark: { value: 'url("data:image/svg+xml,...")' },
      },
    },
  },
})
```

## Semantic Tokens

### Light/Dark Mode Tokens

```tsx
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    semanticTokens: {
      colors: {
        // Background tokens
        bg: {
          DEFAULT: {
            value: { base: '{colors.white}', _dark: '{colors.gray.900}' },
          },
          subtle: {
            value: { base: '{colors.gray.50}', _dark: '{colors.gray.800}' },
          },
          muted: {
            value: { base: '{colors.gray.100}', _dark: '{colors.gray.700}' },
          },
          emphasized: {
            value: { base: '{colors.gray.200}', _dark: '{colors.gray.600}' },
          },
          inverted: {
            value: { base: '{colors.gray.900}', _dark: '{colors.white}' },
          },
        },

        // Foreground/text tokens
        fg: {
          DEFAULT: {
            value: { base: '{colors.gray.900}', _dark: '{colors.gray.50}' },
          },
          muted: {
            value: { base: '{colors.gray.600}', _dark: '{colors.gray.400}' },
          },
          subtle: {
            value: { base: '{colors.gray.500}', _dark: '{colors.gray.500}' },
          },
          inverted: {
            value: { base: '{colors.white}', _dark: '{colors.gray.900}' },
          },
        },

        // Border tokens
        border: {
          DEFAULT: {
            value: { base: '{colors.gray.200}', _dark: '{colors.gray.700}' },
          },
          muted: {
            value: { base: '{colors.gray.100}', _dark: '{colors.gray.800}' },
          },
          emphasized: {
            value: { base: '{colors.gray.300}', _dark: '{colors.gray.600}' },
          },
        },

        // Brand color palette (7 required semantic tokens)
        brand: {
          solid: { value: '{colors.brand.500}' },
          contrast: { value: 'white' },
          fg: {
            value: { base: '{colors.brand.700}', _dark: '{colors.brand.300}' },
          },
          muted: {
            value: { base: '{colors.brand.100}', _dark: '{colors.brand.900}' },
          },
          subtle: {
            value: { base: '{colors.brand.50}', _dark: '{colors.brand.950}' },
          },
          emphasized: {
            value: { base: '{colors.brand.200}', _dark: '{colors.brand.800}' },
          },
          focusRing: { value: '{colors.brand.500}' },
        },

        // Status colors with semantic tokens
        success: {
          solid: { value: '{colors.green.500}' },
          contrast: { value: 'white' },
          fg: {
            value: { base: '{colors.green.700}', _dark: '{colors.green.300}' },
          },
          muted: {
            value: { base: '{colors.green.100}', _dark: '{colors.green.900}' },
          },
          subtle: {
            value: { base: '{colors.green.50}', _dark: '{colors.green.950}' },
          },
          emphasized: {
            value: { base: '{colors.green.200}', _dark: '{colors.green.800}' },
          },
          focusRing: { value: '{colors.green.500}' },
        },

        error: {
          solid: { value: '{colors.red.500}' },
          contrast: { value: 'white' },
          fg: {
            value: { base: '{colors.red.700}', _dark: '{colors.red.300}' },
          },
          muted: {
            value: { base: '{colors.red.100}', _dark: '{colors.red.900}' },
          },
          subtle: {
            value: { base: '{colors.red.50}', _dark: '{colors.red.950}' },
          },
          emphasized: {
            value: { base: '{colors.red.200}', _dark: '{colors.red.800}' },
          },
          focusRing: { value: '{colors.red.500}' },
        },
      },

      // Semantic shadows for dark mode
      shadows: {
        xs: {
          value: {
            base: '0 1px 2px rgba(0, 0, 0, 0.05)',
            _dark: '0 1px 2px rgba(0, 0, 0, 0.4)',
          },
        },
        sm: {
          value: {
            base: '0 1px 3px rgba(0, 0, 0, 0.1)',
            _dark: '0 1px 3px rgba(0, 0, 0, 0.5)',
          },
        },
      },
    },
  },
})
```

### Token Reference Syntax

```tsx
// Reference other tokens with curly braces - full path required
semanticTokens: {
  colors: {
    accent: { value: '{colors.brand.500}' },
    highlight: { value: '{colors.yellow.300}' },

    // Nested references
    primaryButton: {
      bg: { value: '{colors.brand.solid}' },
      text: { value: '{colors.brand.contrast}' },
    },
  },
}
```

## Recipes

### Single-Part Recipe with TypeScript

```tsx
import { defineRecipe } from '@chakra-ui/react'
import type { RecipeVariantProps } from '@chakra-ui/react'

export const buttonRecipe = defineRecipe({
  className: 'button',
  description: 'Custom button styles',

  base: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 'medium',
    borderRadius: 'lg',
    cursor: 'pointer',
    transition: 'all 0.2s',
    _disabled: {
      opacity: 0.5,
      cursor: 'not-allowed',
      pointerEvents: 'none',
    },
    _focusVisible: {
      outline: '2px solid',
      outlineColor: 'brand.focusRing',
      outlineOffset: '2px',
    },
  },

  variants: {
    variant: {
      solid: {
        bg: 'brand.solid',
        color: 'brand.contrast',
        _hover: { bg: 'brand.emphasized' },
        _active: { bg: 'brand.fg' },
      },
      outline: {
        borderWidth: '1px',
        borderColor: 'brand.solid',
        color: 'brand.fg',
        _hover: { bg: 'brand.subtle' },
      },
      ghost: {
        color: 'brand.fg',
        _hover: { bg: 'brand.subtle' },
      },
      link: {
        color: 'brand.fg',
        _hover: { textDecoration: 'underline' },
        padding: 0,
        height: 'auto',
      },
    },

    size: {
      xs: { h: '6', px: '2', fontSize: 'xs', gap: '1' },
      sm: { h: '8', px: '3', fontSize: 'sm', gap: '1.5' },
      md: { h: '10', px: '4', fontSize: 'md', gap: '2' },
      lg: { h: '12', px: '6', fontSize: 'lg', gap: '2' },
      xl: { h: '14', px: '8', fontSize: 'xl', gap: '2.5' },
    },
  },

  compoundVariants: [
    // Solid + large = bold text
    {
      variant: 'solid',
      size: 'lg',
      css: { fontWeight: 'bold' },
    },
    // Solid + xl = extra bold
    {
      variant: 'solid',
      size: 'xl',
      css: { fontWeight: 'bold', letterSpacing: 'wide' },
    },
  ],

  defaultVariants: {
    variant: 'solid',
    size: 'md',
  },
})

// Export type for component props
export type ButtonVariants = RecipeVariantProps<typeof buttonRecipe>

// Usage in component
interface CustomButtonProps extends ButtonVariants {
  children: React.ReactNode
  onClick?: () => void
}
```

### Slot Recipe (Multi-Part) with TypeScript

```tsx
import { defineSlotRecipe } from '@chakra-ui/react'
import type { SlotRecipeVariantProps } from '@chakra-ui/react'

export const cardRecipe = defineSlotRecipe({
  className: 'card',
  slots: ['root', 'header', 'body', 'footer', 'title', 'description'],

  base: {
    root: {
      bg: 'bg',
      borderRadius: 'xl',
      overflow: 'hidden',
    },
    header: {
      p: '4',
      borderBottomWidth: '1px',
      borderColor: 'border',
    },
    body: {
      p: '4',
    },
    footer: {
      p: '4',
      borderTopWidth: '1px',
      borderColor: 'border',
      display: 'flex',
      gap: '2',
    },
    title: {
      fontWeight: 'semibold',
      fontSize: 'lg',
      color: 'fg',
    },
    description: {
      color: 'fg.muted',
      fontSize: 'sm',
    },
  },

  variants: {
    variant: {
      elevated: {
        root: { shadow: 'lg' },
      },
      outline: {
        root: {
          borderWidth: '1px',
          borderColor: 'border',
        },
      },
      filled: {
        root: { bg: 'bg.muted' },
        header: { borderColor: 'transparent' },
        footer: { borderColor: 'transparent' },
      },
      unstyled: {
        root: { bg: 'transparent', borderRadius: 'none' },
        header: { p: '0', borderBottom: 'none' },
        body: { p: '0' },
        footer: { p: '0', borderTop: 'none' },
      },
    },

    size: {
      sm: {
        root: { borderRadius: 'lg' },
        header: { p: '3' },
        body: { p: '3' },
        footer: { p: '3' },
        title: { fontSize: 'md' },
        description: { fontSize: 'xs' },
      },
      md: {
        // Uses base styles
      },
      lg: {
        header: { p: '6' },
        body: { p: '6' },
        footer: { p: '6' },
        title: { fontSize: 'xl' },
      },
    },
  },

  defaultVariants: {
    variant: 'elevated',
    size: 'md',
  },
})

// Export type
export type CardVariants = SlotRecipeVariantProps<typeof cardRecipe>
```

### Adding Recipes to Theme

```tsx
import { createSystem, defaultConfig, defineConfig } from '@chakra-ui/react'
import { buttonRecipe } from './recipes/button'
import { cardRecipe } from './recipes/card'

const config = defineConfig({
  theme: {
    recipes: {
      button: buttonRecipe,
    },
    slotRecipes: {
      card: cardRecipe,
    },
  },
})

export const system = createSystem(defaultConfig, config)
```

## Extending Default Recipes

```tsx
import { defineRecipe, defaultConfig } from '@chakra-ui/react'

// Extend the default button recipe
const extendedButtonRecipe = defineRecipe({
  ...defaultConfig.theme?.recipes?.button,

  variants: {
    ...defaultConfig.theme?.recipes?.button?.variants,

    // Add new variant
    variant: {
      ...defaultConfig.theme?.recipes?.button?.variants?.variant,
      brand: {
        bg: 'brand.solid',
        color: 'brand.contrast',
        _hover: { bg: 'brand.emphasized' },
      },
      danger: {
        bg: 'error.solid',
        color: 'error.contrast',
        _hover: { bg: 'error.emphasized' },
      },
    },

    // Add new size
    size: {
      ...defaultConfig.theme?.recipes?.button?.variants?.size,
      '2xl': { h: '16', px: '10', fontSize: '2xl' },
    },
  },
})
```

## Breakpoints

```tsx
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    breakpoints: {
      sm: '480px',
      md: '768px',
      lg: '992px',
      xl: '1280px',
      '2xl': '1536px',
    },
  },
})

// Usage in components
<Box
  width={{ base: '100%', sm: '100%', md: '50%', lg: '33%', xl: '25%' }}
  display={{ base: 'block', md: 'flex' }}
  p={{ base: '2', md: '4', lg: '6' }}
/>

// Responsive tokens in theme
const config = defineConfig({
  theme: {
    tokens: {
      spacing: {
        container: {
          value: { base: '1rem', md: '2rem', lg: '4rem' },
        },
      },
    },
  },
})
```

## Global Styles

```tsx
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  globalCss: {
    // Reset/normalize
    '*, *::before, *::after': {
      boxSizing: 'border-box',
    },

    // Base styles
    'html, body': {
      bg: 'bg',
      color: 'fg',
      fontFamily: 'body',
      lineHeight: 'normal',
      minHeight: '100vh',
    },

    // Selection
    '::selection': {
      bg: 'brand.subtle',
      color: 'brand.fg',
    },

    // Links
    a: {
      color: 'brand.fg',
      textDecoration: 'none',
      _hover: { textDecoration: 'underline' },
    },

    // Focus visible
    ':focus-visible': {
      outline: '2px solid',
      outlineColor: 'brand.focusRing',
      outlineOffset: '2px',
    },

    // Scrollbar (webkit)
    '::-webkit-scrollbar': {
      width: '8px',
      height: '8px',
    },
    '::-webkit-scrollbar-track': {
      bg: 'bg.subtle',
    },
    '::-webkit-scrollbar-thumb': {
      bg: 'border.emphasized',
      borderRadius: 'full',
    },
  },
})
```

## Layer Styles

```tsx
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    layerStyles: {
      card: {
        bg: 'bg',
        borderRadius: 'xl',
        shadow: 'md',
        p: '4',
      },
      cardOutline: {
        bg: 'bg',
        borderRadius: 'xl',
        borderWidth: '1px',
        borderColor: 'border',
        p: '4',
      },
      subtle: {
        bg: 'bg.subtle',
        borderRadius: 'lg',
        p: '3',
      },
      elevated: {
        bg: 'bg',
        borderRadius: 'xl',
        shadow: 'xl',
        p: '6',
      },
      interactive: {
        bg: 'bg',
        borderRadius: 'lg',
        cursor: 'pointer',
        transition: 'all 0.2s',
        _hover: { bg: 'bg.subtle' },
        _active: { bg: 'bg.muted' },
      },
    },
  },
})

// Usage
<Box layerStyle="card">Card content</Box>
<Box layerStyle="interactive" onClick={handleClick}>Clickable</Box>
```

## Text Styles

```tsx
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    textStyles: {
      h1: {
        fontSize: { base: '3xl', md: '4xl', lg: '5xl' },
        fontWeight: 'bold',
        lineHeight: 'tight',
        letterSpacing: 'tight',
      },
      h2: {
        fontSize: { base: '2xl', md: '3xl' },
        fontWeight: 'semibold',
        lineHeight: 'tight',
      },
      h3: {
        fontSize: { base: 'xl', md: '2xl' },
        fontWeight: 'semibold',
        lineHeight: 'snug',
      },
      h4: {
        fontSize: { base: 'lg', md: 'xl' },
        fontWeight: 'medium',
        lineHeight: 'snug',
      },
      body: {
        fontSize: 'md',
        lineHeight: 'relaxed',
      },
      bodyLarge: {
        fontSize: 'lg',
        lineHeight: 'relaxed',
      },
      caption: {
        fontSize: 'sm',
        color: 'fg.muted',
        lineHeight: 'normal',
      },
      overline: {
        fontSize: 'xs',
        fontWeight: 'semibold',
        textTransform: 'uppercase',
        letterSpacing: 'wider',
        color: 'fg.muted',
      },
    },
  },
})

// Usage
<Text textStyle="h1">Main Heading</Text>
<Text textStyle="body">Paragraph text here.</Text>
<Text textStyle="caption">Small helper text</Text>
```

## Custom Conditions

```tsx
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  conditions: {
    // Color mode
    light: '[data-theme=light] &',
    dark: '[data-theme=dark] &',

    // Direction
    rtl: '[dir=rtl] &',
    ltr: '[dir=ltr] &',

    // States
    hover: '&:is(:hover, [data-hover])',
    focus: '&:is(:focus, [data-focus])',
    focusVisible: '&:is(:focus-visible, [data-focus-visible])',
    focusWithin: '&:focus-within',
    active: '&:is(:active, [data-active])',
    disabled: '&:is(:disabled, [disabled], [data-disabled])',
    readOnly: '&:is(:read-only, [data-readonly])',
    checked: '&:is(:checked, [data-checked])',
    indeterminate: '&:is(:indeterminate, [data-indeterminate])',
    invalid: '&:is(:invalid, [data-invalid])',
    required: '&:is(:required, [data-required])',
    empty: '&:is(:empty, [data-empty])',

    // Custom states
    expanded: '&[data-expanded]',
    selected: '&[data-selected]',
    loading: '&[data-loading]',

    // Pseudo elements
    before: '&::before',
    after: '&::after',
    placeholder: '&::placeholder',

    // Media queries
    motionReduce: '@media (prefers-reduced-motion: reduce)',
    motionSafe: '@media (prefers-reduced-motion: no-preference)',
    print: '@media print',
    landscape: '@media (orientation: landscape)',
    portrait: '@media (orientation: portrait)',
  },
})

// Usage
<Box
  _hover={{ bg: 'bg.subtle' }}
  _focusVisible={{ outline: '2px solid blue' }}
  _disabled={{ opacity: 0.5 }}
  _motionReduce={{ transition: 'none' }}
>
  Interactive element
</Box>
```

## Using Theme Tokens in Code

```tsx
import type { FC } from 'react'
import { useToken, useTheme } from '@chakra-ui/react'

const TokenExample: FC = () => {
  // Get single token value
  const [brandColor] = useToken('colors', ['brand.500'])

  // Get multiple tokens
  const [sm, md, lg] = useToken('spacing', ['sm', 'md', 'lg'])

  // Get with fallback
  const [primary] = useToken('colors', ['brand.primary'], '#0073e6')

  // Access full theme/system
  const theme = useTheme()

  // Use in inline styles or pass to non-Chakra components
  return (
    <div style={{ backgroundColor: brandColor, padding: md }}>
      Token values
    </div>
  )
}

// Type-safe token access
import type { Token } from '@chakra-ui/react'

const getColorToken = (color: Token<'colors'>): string => {
  // Type-safe color token
  return color
}
```

## CSS Variables

Chakra generates CSS variables automatically:

```css
:root {
  --app-colors-brand-500: #0073e6;
  --app-colors-brand-solid: var(--app-colors-brand-500);
  --app-spacing-md: 1rem;
  --app-radii-lg: 0.5rem;
  --app-fonts-body: Inter, sans-serif;
}

[data-theme="dark"] {
  --app-colors-bg: var(--app-colors-gray-900);
  --app-colors-fg: var(--app-colors-gray-50);
}
```

Access in custom CSS or non-Chakra components:

```css
.custom-element {
  background: var(--app-colors-brand-500);
  padding: var(--app-spacing-md);
  border-radius: var(--app-radii-lg);
  font-family: var(--app-fonts-body);
}
```

```tsx
// In styled-components or emotion
const CustomDiv = styled.div`
  background: var(--app-colors-brand-500);
  padding: var(--app-spacing-md);
`
```

## Font Loading (Next.js)

```tsx
// app/layout.tsx
import { Inter } from 'next/font/google'
import { Provider } from '@/components/ui/provider'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
})

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <Provider>{children}</Provider>
      </body>
    </html>
  )
}
```

```tsx
// theme.ts
const config = defineConfig({
  theme: {
    tokens: {
      fonts: {
        heading: { value: 'var(--font-inter), sans-serif' },
        body: { value: 'var(--font-inter), sans-serif' },
      },
    },
  },
})
```
