# Chakra UI Accessibility Reference

Accessibility patterns and best practices for Chakra UI v3.

## Overview

Chakra UI is built with accessibility in mind, but proper implementation requires understanding key patterns. This guide covers ARIA attributes, keyboard navigation, focus management, and screen reader considerations.

## Built-in Accessibility

Chakra components include accessibility features by default:

- Proper ARIA roles and attributes
- Keyboard navigation support
- Focus management for overlays
- Screen reader announcements

## Keyboard Navigation

### Focus Visible Styles

```tsx
import { defineConfig } from '@chakra-ui/react'

// Configure global focus styles
const config = defineConfig({
  globalCss: {
    ':focus-visible': {
      outline: '2px solid',
      outlineColor: 'brand.focusRing',
      outlineOffset: '2px',
    },
    // Remove default focus outline (replaced by focus-visible)
    ':focus:not(:focus-visible)': {
      outline: 'none',
    },
  },
})
```

### Skip Links

```tsx
import type { FC } from 'react'
import { Link, Box } from '@chakra-ui/react'

const SkipLink: FC = () => {
  return (
    <Link
      href="#main-content"
      position="absolute"
      top="-40px"
      left="0"
      bg="brand.solid"
      color="brand.contrast"
      p="2"
      zIndex="skipLink"
      _focusVisible={{
        top: '0',
      }}
    >
      Skip to main content
    </Link>
  )
}

// In your layout
const Layout: FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <>
      <SkipLink />
      <header>{/* Nav */}</header>
      <Box as="main" id="main-content" tabIndex={-1}>
        {children}
      </Box>
    </>
  )
}
```

### Keyboard Shortcuts

```tsx
import type { FC } from 'react'
import { useEffect, useCallback } from 'react'
import { Kbd, Text, HStack } from '@chakra-ui/react'

interface KeyboardShortcutProps {
  keys: string[]
  onActivate: () => void
  description: string
}

const useKeyboardShortcut = (
  keys: string[],
  callback: () => void,
  options: { ctrl?: boolean; shift?: boolean; alt?: boolean } = {}
): void => {
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      const { ctrl = false, shift = false, alt = false } = options

      if (ctrl !== event.ctrlKey) return
      if (shift !== event.shiftKey) return
      if (alt !== event.altKey) return

      if (keys.includes(event.key.toLowerCase())) {
        event.preventDefault()
        callback()
      }
    },
    [keys, callback, options]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}

// Usage
const SearchModal: FC = () => {
  const [open, setOpen] = useState(false)

  useKeyboardShortcut(['k'], () => setOpen(true), { ctrl: true })

  return (
    <>
      <HStack>
        <Text fontSize="sm" color="fg.muted">Search</Text>
        <Kbd>Ctrl</Kbd>
        <Kbd>K</Kbd>
      </HStack>
      {/* Dialog component */}
    </>
  )
}
```

## Focus Management

### Focus Trap in Modals

Chakra's Dialog component automatically traps focus. For custom implementations:

```tsx
import type { FC } from 'react'
import { useRef, useEffect } from 'react'
import { Dialog, Portal, Button } from '@chakra-ui/react'

interface AccessibleDialogProps {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  initialFocusRef?: React.RefObject<HTMLElement>
  finalFocusRef?: React.RefObject<HTMLElement>
}

const AccessibleDialog: FC<AccessibleDialogProps> = ({
  open,
  onClose,
  title,
  children,
  initialFocusRef,
  finalFocusRef,
}) => {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(details) => !details.open && onClose()}
      initialFocusEl={initialFocusRef?.current ?? undefined}
      finalFocusEl={finalFocusRef?.current ?? undefined}
    >
      <Portal>
        <Dialog.Backdrop />
        <Dialog.Positioner>
          <Dialog.Content>
            <Dialog.Header>
              <Dialog.Title>{title}</Dialog.Title>
            </Dialog.Header>
            <Dialog.Body>{children}</Dialog.Body>
            <Dialog.CloseTrigger />
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}
```

### Focus Restoration

```tsx
import type { FC } from 'react'
import { useRef, useState } from 'react'
import { Button, Dialog, Portal } from '@chakra-ui/react'

const FocusRestorationExample: FC = () => {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)

  return (
    <>
      <Button ref={triggerRef} onClick={() => setOpen(true)}>
        Open Dialog
      </Button>

      <Dialog.Root
        open={open}
        onOpenChange={(details) => setOpen(details.open)}
        finalFocusEl={triggerRef.current ?? undefined}
      >
        <Portal>
          <Dialog.Backdrop />
          <Dialog.Positioner>
            <Dialog.Content>
              <Dialog.Header>
                <Dialog.Title>Dialog</Dialog.Title>
              </Dialog.Header>
              <Dialog.Body>
                Focus returns to trigger button on close.
              </Dialog.Body>
              <Dialog.CloseTrigger />
            </Dialog.Content>
          </Dialog.Positioner>
        </Portal>
      </Dialog.Root>
    </>
  )
}
```

### Managing Focus Programmatically

```tsx
import type { FC } from 'react'
import { useRef } from 'react'
import { Input, Button, Stack } from '@chakra-ui/react'

const FocusManagementExample: FC = () => {
  const inputRef = useRef<HTMLInputElement>(null)
  const submitRef = useRef<HTMLButtonElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Enter') {
      e.preventDefault()
      submitRef.current?.focus()
    }
  }

  const focusInput = (): void => {
    inputRef.current?.focus()
  }

  return (
    <Stack gap="4">
      <Input
        ref={inputRef}
        placeholder="Press Enter to focus submit"
        onKeyDown={handleKeyDown}
      />
      <Button ref={submitRef} colorPalette="blue">
        Submit
      </Button>
      <Button variant="outline" onClick={focusInput}>
        Focus Input
      </Button>
    </Stack>
  )
}
```

## ARIA Patterns

### Live Regions

```tsx
import type { FC } from 'react'
import { Box, VisuallyHidden } from '@chakra-ui/react'

interface LiveRegionProps {
  message: string
  assertive?: boolean
}

const LiveRegion: FC<LiveRegionProps> = ({ message, assertive = false }) => {
  return (
    <VisuallyHidden>
      <Box
        aria-live={assertive ? 'assertive' : 'polite'}
        aria-atomic="true"
        role="status"
      >
        {message}
      </Box>
    </VisuallyHidden>
  )
}

// Usage for form validation
const FormWithAnnouncement: FC = () => {
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  return (
    <form>
      {/* Form fields */}
      <LiveRegion message={error ?? success ?? ''} assertive={!!error} />
    </form>
  )
}
```

### Accessible Labels

```tsx
import type { FC } from 'react'
import { Field, Input, VisuallyHidden } from '@chakra-ui/react'

// Visible label (preferred)
const VisibleLabelInput: FC = () => (
  <Field.Root>
    <Field.Label>Email Address</Field.Label>
    <Input type="email" />
  </Field.Root>
)

// Hidden label for icon-only inputs
const IconOnlyInput: FC = () => (
  <Field.Root>
    <VisuallyHidden>
      <Field.Label>Search</Field.Label>
    </VisuallyHidden>
    <Input type="search" placeholder="Search..." />
  </Field.Root>
)

// Using aria-label for simple cases
const AriaLabelInput: FC = () => (
  <Input aria-label="Search" type="search" placeholder="Search..." />
)

// Using aria-labelledby for complex labels
const ComplexLabelInput: FC = () => (
  <>
    <Box id="email-label">
      <Text fontWeight="bold">Email</Text>
      <Text fontSize="sm" color="fg.muted">We'll send confirmation here</Text>
    </Box>
    <Input aria-labelledby="email-label" type="email" />
  </>
)
```

### Accessible Descriptions

```tsx
import type { FC } from 'react'
import { Field, Input, Text } from '@chakra-ui/react'

const DescribedInput: FC = () => (
  <Field.Root>
    <Field.Label>Password</Field.Label>
    <Input type="password" aria-describedby="password-help password-error" />
    <Text id="password-help" fontSize="sm" color="fg.muted">
      Must be at least 8 characters
    </Text>
    <Text id="password-error" fontSize="sm" color="error.fg">
      Password is too short
    </Text>
  </Field.Root>
)
```

### Role and State Management

```tsx
import type { FC } from 'react'
import { Box, Button } from '@chakra-ui/react'

interface ExpandableSectionProps {
  title: string
  children: React.ReactNode
}

const ExpandableSection: FC<ExpandableSectionProps> = ({ title, children }) => {
  const [expanded, setExpanded] = useState(false)
  const contentId = useId()

  return (
    <Box>
      <Button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={contentId}
      >
        {title}
      </Button>
      <Box
        id={contentId}
        hidden={!expanded}
        role="region"
        aria-labelledby={`${contentId}-trigger`}
      >
        {children}
      </Box>
    </Box>
  )
}
```

## Screen Reader Considerations

### Visually Hidden Content

```tsx
import type { FC } from 'react'
import { VisuallyHidden, Button, Badge, HStack } from '@chakra-ui/react'
import { LuShoppingCart } from 'react-icons/lu'

// Icon button with screen reader text
const CartButton: FC<{ itemCount: number }> = ({ itemCount }) => (
  <Button variant="ghost" aria-label={`Shopping cart with ${itemCount} items`}>
    <LuShoppingCart />
    <Badge>{itemCount}</Badge>
    <VisuallyHidden>items in cart</VisuallyHidden>
  </Button>
)

// Decorative vs informative icons
const StatusIndicator: FC<{ status: 'online' | 'offline' }> = ({ status }) => (
  <HStack>
    {/* Decorative icon - hide from screen readers */}
    <Box
      w="2"
      h="2"
      rounded="full"
      bg={status === 'online' ? 'green.500' : 'gray.400'}
      aria-hidden="true"
    />
    {/* Or provide alternative text */}
    <VisuallyHidden>{status === 'online' ? 'Online' : 'Offline'}</VisuallyHidden>
    <Text>User Name</Text>
  </HStack>
)
```

### Announcing Dynamic Content

```tsx
import type { FC } from 'react'
import { useState, useEffect } from 'react'
import { Box, Spinner, Text, VisuallyHidden } from '@chakra-ui/react'

interface LoadingStateProps {
  isLoading: boolean
  children: React.ReactNode
}

const LoadingState: FC<LoadingStateProps> = ({ isLoading, children }) => {
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    if (isLoading) {
      setAnnouncement('Loading content')
    } else {
      setAnnouncement('Content loaded')
    }
  }, [isLoading])

  return (
    <>
      <VisuallyHidden aria-live="polite" aria-atomic="true">
        {announcement}
      </VisuallyHidden>

      {isLoading ? (
        <Box textAlign="center" py="8">
          <Spinner size="lg" />
          <Text mt="2" color="fg.muted">Loading...</Text>
        </Box>
      ) : (
        children
      )}
    </>
  )
}
```

### Table Accessibility

```tsx
import type { FC } from 'react'
import { Table, VisuallyHidden } from '@chakra-ui/react'

interface DataItem {
  id: string
  name: string
  email: string
  status: 'active' | 'inactive'
}

interface AccessibleTableProps {
  data: DataItem[]
  caption: string
}

const AccessibleTable: FC<AccessibleTableProps> = ({ data, caption }) => {
  return (
    <Table.Root>
      {/* Screen reader caption */}
      <VisuallyHidden as="caption">{caption}</VisuallyHidden>

      <Table.Header>
        <Table.Row>
          <Table.ColumnHeader scope="col">Name</Table.ColumnHeader>
          <Table.ColumnHeader scope="col">Email</Table.ColumnHeader>
          <Table.ColumnHeader scope="col">Status</Table.ColumnHeader>
          <Table.ColumnHeader scope="col">
            <VisuallyHidden>Actions</VisuallyHidden>
          </Table.ColumnHeader>
        </Table.Row>
      </Table.Header>
      <Table.Body>
        {data.map((item) => (
          <Table.Row key={item.id}>
            <Table.Cell>{item.name}</Table.Cell>
            <Table.Cell>{item.email}</Table.Cell>
            <Table.Cell>
              <Badge colorPalette={item.status === 'active' ? 'green' : 'gray'}>
                {item.status}
              </Badge>
            </Table.Cell>
            <Table.Cell>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Edit ${item.name}`}
              >
                Edit
              </Button>
            </Table.Cell>
          </Table.Row>
        ))}
      </Table.Body>
    </Table.Root>
  )
}
```

## Form Accessibility

### Error Handling

```tsx
import type { FC } from 'react'
import { useId } from 'react'
import { Field, Input, Stack, Alert } from '@chakra-ui/react'

interface FormFieldProps {
  label: string
  error?: string
  required?: boolean
  type?: string
}

const AccessibleFormField: FC<FormFieldProps> = ({
  label,
  error,
  required = false,
  type = 'text',
}) => {
  const id = useId()
  const errorId = `${id}-error`
  const helpId = `${id}-help`

  return (
    <Field.Root invalid={!!error} required={required}>
      <Field.Label htmlFor={id}>
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </Field.Label>
      <Input
        id={id}
        type={type}
        aria-invalid={!!error}
        aria-describedby={error ? errorId : undefined}
        aria-required={required}
      />
      {error && (
        <Field.ErrorText id={errorId} role="alert">
          {error}
        </Field.ErrorText>
      )}
    </Field.Root>
  )
}

// Form-level error summary
interface FormErrorSummaryProps {
  errors: Record<string, string>
}

const FormErrorSummary: FC<FormErrorSummaryProps> = ({ errors }) => {
  const errorEntries = Object.entries(errors)

  if (errorEntries.length === 0) return null

  return (
    <Alert.Root status="error" role="alert" aria-live="assertive">
      <Alert.Indicator />
      <Alert.Content>
        <Alert.Title>Please fix the following errors:</Alert.Title>
        <Alert.Description>
          <Stack as="ul" gap="1" pl="4">
            {errorEntries.map(([field, message]) => (
              <li key={field}>
                <a href={`#${field}`}>{message}</a>
              </li>
            ))}
          </Stack>
        </Alert.Description>
      </Alert.Content>
    </Alert.Root>
  )
}
```

### Required Fields

```tsx
import type { FC } from 'react'
import { Field, Input, Text, Stack } from '@chakra-ui/react'

const RequiredFieldsForm: FC = () => {
  return (
    <Stack gap="4">
      {/* Indicate required fields at form level */}
      <Text fontSize="sm" color="fg.muted">
        <span aria-hidden="true">*</span> Required fields
      </Text>

      <Field.Root required>
        <Field.Label>
          Name <span aria-hidden="true">*</span>
        </Field.Label>
        <Input aria-required="true" />
        <Field.RequiredIndicator />
      </Field.Root>

      <Field.Root>
        <Field.Label>Phone (optional)</Field.Label>
        <Input />
      </Field.Root>
    </Stack>
  )
}
```

## Color and Contrast

### Ensuring Sufficient Contrast

```tsx
import { defineConfig } from '@chakra-ui/react'

// Define colors with accessibility in mind
const config = defineConfig({
  theme: {
    semanticTokens: {
      colors: {
        // Ensure 4.5:1 contrast ratio for normal text
        // Ensure 3:1 contrast ratio for large text and UI components
        fg: {
          DEFAULT: {
            value: { base: '#1a1a1a', _dark: '#f5f5f5' }, // High contrast
          },
          muted: {
            value: { base: '#666666', _dark: '#a3a3a3' }, // Still accessible
          },
          // Avoid light grays on white backgrounds
          subtle: {
            value: { base: '#737373', _dark: '#8c8c8c' }, // Minimum 4.5:1
          },
        },
      },
    },
  },
})
```

### Color-Independent Information

```tsx
import type { FC } from 'react'
import { Badge, HStack, Text } from '@chakra-ui/react'
import { LuCheck, LuX, LuAlertCircle } from 'react-icons/lu'

type Status = 'success' | 'error' | 'warning'

interface StatusBadgeProps {
  status: Status
  label: string
}

// Don't rely on color alone - use icons and text
const AccessibleStatusBadge: FC<StatusBadgeProps> = ({ status, label }) => {
  const icons: Record<Status, React.ReactNode> = {
    success: <LuCheck aria-hidden="true" />,
    error: <LuX aria-hidden="true" />,
    warning: <LuAlertCircle aria-hidden="true" />,
  }

  const colors: Record<Status, string> = {
    success: 'green',
    error: 'red',
    warning: 'orange',
  }

  return (
    <Badge colorPalette={colors[status]}>
      <HStack gap="1">
        {icons[status]}
        <Text>{label}</Text>
      </HStack>
    </Badge>
  )
}
```

## Motion and Animation

### Respecting User Preferences

```tsx
import { defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    tokens: {
      durations: {
        normal: { value: '200ms' },
      },
    },
  },
  globalCss: {
    // Reduce or remove animations for users who prefer reduced motion
    '@media (prefers-reduced-motion: reduce)': {
      '*': {
        animationDuration: '0.01ms !important',
        animationIterationCount: '1 !important',
        transitionDuration: '0.01ms !important',
      },
    },
  },
})
```

```tsx
import type { FC } from 'react'
import { Box } from '@chakra-ui/react'

const AnimatedComponent: FC = () => {
  return (
    <Box
      transition="transform 0.2s"
      _hover={{ transform: 'scale(1.05)' }}
      _motionReduce={{
        transition: 'none',
        _hover: { transform: 'none' },
      }}
    >
      Hover me
    </Box>
  )
}
```

## Testing Accessibility

### Checklist

1. **Keyboard Navigation**
   - Can all interactive elements be reached with Tab?
   - Can all actions be performed with keyboard alone?
   - Is focus visible at all times?
   - Does focus order make sense?

2. **Screen Readers**
   - Do all images have alt text?
   - Are form fields properly labeled?
   - Are error messages announced?
   - Is dynamic content announced via live regions?

3. **Visual**
   - Is contrast ratio at least 4.5:1 for text?
   - Is information conveyed by more than just color?
   - Does content reflow at 200% zoom?

4. **Structure**
   - Are headings used hierarchically (h1 -> h2 -> h3)?
   - Are landmark regions present (main, nav, aside)?
   - Do lists use proper list markup?

### Automated Testing

```tsx
// In your test files
import { render } from '@testing-library/react'
import { axe, toHaveNoViolations } from 'jest-axe'

expect.extend(toHaveNoViolations)

describe('Accessibility', () => {
  it('should have no accessibility violations', async () => {
    const { container } = render(<YourComponent />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
```

### Manual Testing Tools

- **Browser DevTools**: Accessibility inspector
- **axe DevTools**: Browser extension for automated checks
- **NVDA/VoiceOver**: Screen reader testing
- **Keyboard only**: Unplug your mouse and navigate
