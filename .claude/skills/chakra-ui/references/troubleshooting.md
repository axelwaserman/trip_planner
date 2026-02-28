# Chakra UI Troubleshooting

Common issues and solutions for Chakra UI v3.

## Provider Issues

### "ChakraProvider not found" or "Cannot read property 'theme'"

**Cause**: Components rendered outside ChakraProvider.

**Solution**:

```tsx
// Ensure ChakraProvider wraps your entire app
import { ChakraProvider, defaultSystem } from '@chakra-ui/react'

function App({ children }: { children: React.ReactNode }) {
  return (
    <ChakraProvider value={defaultSystem}>
      {children}
    </ChakraProvider>
  )
}

// For Next.js App Router
// app/layout.tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ChakraProvider value={defaultSystem}>
          {children}
        </ChakraProvider>
      </body>
    </html>
  )
}
```

### "Invalid value for `value` prop"

**Cause**: Using wrong prop name or value type for ChakraProvider.

**Solution**:

```tsx
// Wrong
<ChakraProvider theme={myTheme}>

// Correct - v3 uses `value` and requires a system
import { createSystem, defaultConfig } from '@chakra-ui/react'

const system = createSystem(defaultConfig)
<ChakraProvider value={system}>
```

## Hydration Errors

### "Hydration failed because server HTML doesn't match client"

**Cause**: Server and client render different content, often due to color mode.

**Solutions**:

```tsx
// 1. Add suppressHydrationWarning to html tag
<html lang="en" suppressHydrationWarning>

// 2. Use ClientOnly wrapper for color-mode-dependent UI
import { ClientOnly, Skeleton } from '@chakra-ui/react'

<ClientOnly fallback={<Skeleton height="40px" />}>
  <ColorModeButton />
</ClientOnly>

// 3. For custom color mode UI, defer rendering
import { useEffect, useState } from 'react'

function ColorModeAwareComponent() {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) return null

  return <YourComponent />
}
```

### Hydration error with Portal components

**Cause**: Portals render to document.body which may not exist on server.

**Solution**:

```tsx
import { Portal } from '@chakra-ui/react'

// Portals only render on client by default, but ensure proper structure
<Dialog.Root>
  <Dialog.Trigger>Open</Dialog.Trigger>
  <Portal>  {/* This handles client-only rendering */}
    <Dialog.Backdrop />
    <Dialog.Positioner>
      <Dialog.Content>...</Dialog.Content>
    </Dialog.Positioner>
  </Portal>
</Dialog.Root>
```

## Z-Index Issues

### Modal/Menu/Popover appears behind other elements

**Cause**: Missing Portal wrapper or conflicting z-index.

**Solution**:

```tsx
// Always wrap overlay content in Portal
import { Menu, Portal } from '@chakra-ui/react'

<Menu.Root>
  <Menu.Trigger>Open</Menu.Trigger>
  <Portal>  {/* Essential for proper z-index */}
    <Menu.Positioner>
      <Menu.Content>
        <Menu.Item value="edit">Edit</Menu.Item>
      </Menu.Content>
    </Menu.Positioner>
  </Portal>
</Menu.Root>

// For custom z-index, use theme tokens
const config = defineConfig({
  theme: {
    tokens: {
      zIndex: {
        modal: { value: 1400 },
        popover: { value: 1500 },
        tooltip: { value: 1800 },
      },
    },
  },
})
```

### Stacking context issues

**Cause**: Parent elements create new stacking contexts.

**Solution**:

```tsx
// Avoid transform, filter, or will-change on parent elements
// Or ensure Portal renders to document.body

// If you must have transforms, use higher z-index
<Box position="relative" zIndex="docked">
  <Menu.Root>
    ...
  </Menu.Root>
</Box>
```

## Style Props Not Working

### Style props have no effect

**Cause**: Using wrong prop names or non-token values with `strictTokens`.

**Solution**:

```tsx
// Check prop names - some changed in v3
// Wrong
<Box marginTop="4" />

// Correct - use shorthand or full name consistently
<Box mt="4" />
<Box marginTop="4" />  // Both work, but be consistent

// If using strictTokens: true, only token values work
// Wrong with strictTokens
<Box p="20px" />

// Correct
<Box p="5" />  // Uses spacing token

// Or disable strictTokens for flexibility
const config = defineConfig({
  strictTokens: false,  // Allow arbitrary values
})
```

### Responsive props not working

**Cause**: Incorrect responsive syntax.

**Solution**:

```tsx
// Object syntax (recommended)
<Box
  p={{ base: '2', md: '4', lg: '6' }}
  display={{ base: 'block', md: 'flex' }}
/>

// Array syntax (mobile-first: base, sm, md, lg, xl, 2xl)
<Box p={['2', '3', '4', '5', '6']} />

// Don't mix syntaxes
// Wrong
<Box p={{ base: '2', '4', lg: '6' }} />

// Correct
<Box p={{ base: '2', md: '4', lg: '6' }} />
```

## Color Mode Issues

### Color mode not persisting

**Cause**: Storage or cookie not configured.

**Solution**:

```tsx
// Chakra v3 handles persistence automatically via cookies
// Ensure your server can read cookies

// For Next.js, color mode should work out of the box
// For other frameworks, check cookie settings

// Manual control if needed
import { useColorMode } from '@chakra-ui/react'

function Component() {
  const { colorMode, setColorMode, toggleColorMode } = useColorMode()

  // Force specific mode
  useEffect(() => {
    setColorMode('dark')
  }, [])
}
```

### Flash of wrong color mode

**Cause**: Initial render before color mode is determined.

**Solution**:

```tsx
// 1. Use semantic tokens that handle both modes
<Box bg="bg" color="fg" />

// 2. Add color-scheme to html
<html style={{ colorScheme: 'dark light' }}>

// 3. Use suppressHydrationWarning
<html suppressHydrationWarning>

// 4. Prevent flash with script (if using custom implementation)
// Add to head before any content
<script dangerouslySetInnerHTML={{
  __html: `
    try {
      const mode = localStorage.getItem('chakra-ui-color-mode')
      if (mode) document.documentElement.dataset.theme = mode
    } catch (e) {}
  `
}} />
```

## TypeScript Issues

### "Property does not exist on type"

**Cause**: Missing type definitions or incorrect prop types.

**Solution**:

```tsx
// Import types explicitly
import type { BoxProps, ButtonProps } from '@chakra-ui/react'

interface CustomButtonProps extends ButtonProps {
  customProp?: string
}

// For style props, use SystemStyleObject
import type { SystemStyleObject } from '@chakra-ui/react'

const styles: SystemStyleObject = {
  bg: 'blue.500',
  _hover: { bg: 'blue.600' },
}

// For recipe variants
import type { RecipeVariantProps } from '@chakra-ui/react'

type ButtonVariants = RecipeVariantProps<typeof buttonRecipe>
```

### Theme token types not recognized

**Cause**: Custom tokens not typed.

**Solution**:

```tsx
// Create type declaration file: chakra.d.ts
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    tokens: {
      colors: {
        brand: {
          500: { value: '#0073e6' },
        },
      },
    },
  },
})

type Config = typeof config

declare module '@chakra-ui/react' {
  export interface SystemConfig extends Config {}
}
```

## Build Issues

### "Module not found" errors

**Cause**: Incorrect imports or missing dependencies.

**Solution**:

```bash
# Ensure all peer dependencies are installed
npm install @chakra-ui/react @emotion/react

# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

### Bundle size too large

**Cause**: Importing entire library.

**Solution**:

```tsx
// Chakra v3 supports tree-shaking by default
// But ensure you're not importing everything

// Good - specific imports
import { Button, Box } from '@chakra-ui/react'

// Avoid star imports in production
// import * as Chakra from '@chakra-ui/react'

// Check bundle analyzer
npm install @next/bundle-analyzer  # For Next.js
```

## Form Issues

### Form validation not showing errors

**Cause**: Missing `invalid` prop or error display.

**Solution**:

```tsx
import { Field, Input } from '@chakra-ui/react'

// Ensure invalid prop is set correctly
<Field.Root invalid={!!errors.email}>
  <Field.Label>Email</Field.Label>
  <Input type="email" />
  {errors.email && (
    <Field.ErrorText>{errors.email.message}</Field.ErrorText>
  )}
</Field.Root>
```

### Input not updating

**Cause**: Controlled component without proper handlers.

**Solution**:

```tsx
// For controlled inputs
const [value, setValue] = useState('')

<Input
  value={value}
  onChange={(e) => setValue(e.target.value)}
/>

// For uncontrolled with react-hook-form
const { register } = useForm()

<Input {...register('email')} />
```

## Performance Issues

### Components re-rendering unnecessarily

**Cause**: Inline style objects or callbacks.

**Solution**:

```tsx
// Bad - creates new object every render
<Box sx={{ bg: 'blue.500' }}>

// Good - use style props directly
<Box bg="blue.500">

// Bad - inline callback
<Button onClick={() => handleClick(id)}>

// Good - memoized callback
const handleButtonClick = useCallback(() => handleClick(id), [id])
<Button onClick={handleButtonClick}>

// For complex styles, define outside component
const cardStyles = {
  bg: 'bg',
  p: '4',
  rounded: 'lg',
} as const

function Card() {
  return <Box {...cardStyles}>...</Box>
}
```

### Slow initial load

**Cause**: Large bundle or blocking CSS.

**Solution**:

```tsx
// 1. Use dynamic imports for heavy components
import dynamic from 'next/dynamic'

const HeavyChart = dynamic(() => import('./HeavyChart'), {
  loading: () => <Skeleton height="400px" />,
})

// 2. Lazy load dialogs/modals
const Dialog = dynamic(() =>
  import('@chakra-ui/react').then((mod) => mod.Dialog)
)

// 3. Split theme configuration
// Load only essential theme on initial load
```

## Common Mistakes

### Using `as` prop incorrectly

```tsx
// Wrong - as expects component, not string for some cases
<Dialog.Trigger as="button">

// Correct - use asChild for render delegation
<Dialog.Trigger asChild>
  <Button>Open</Button>
</Dialog.Trigger>
```

### Missing compound component parts

```tsx
// Wrong - missing required parts
<Checkbox.Root>
  <Checkbox.Label>Option</Checkbox.Label>
</Checkbox.Root>

// Correct - include HiddenInput and Control
<Checkbox.Root>
  <Checkbox.HiddenInput />
  <Checkbox.Control>
    <Checkbox.Indicator />
  </Checkbox.Control>
  <Checkbox.Label>Option</Checkbox.Label>
</Checkbox.Root>
```

### Forgetting to handle open state

```tsx
// Wrong - no state management
<Dialog.Root>
  <Dialog.Trigger>Open</Dialog.Trigger>
  <Dialog.Content>...</Dialog.Content>
</Dialog.Root>

// Correct - manage state if you need programmatic control
const [open, setOpen] = useState(false)

<Dialog.Root open={open} onOpenChange={(e) => setOpen(e.open)}>
  ...
</Dialog.Root>

// Or use uncontrolled (simpler for basic cases)
<Dialog.Root>
  <Dialog.Trigger asChild>
    <Button>Open</Button>
  </Dialog.Trigger>
  ...
</Dialog.Root>
```

## Getting Help

1. **Check official docs**: https://chakra-ui.com/docs
2. **Search GitHub issues**: https://github.com/chakra-ui/chakra-ui/issues
3. **Discord community**: https://discord.gg/chakra-ui
4. **Stack Overflow**: Tag with `chakra-ui`

When reporting issues, include:
- Chakra UI version
- React version
- Framework (Next.js, Vite, etc.)
- Minimal reproduction code
- Error messages
