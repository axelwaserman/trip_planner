# Chakra UI Integrations

Integration patterns for Next.js, TypeScript, form libraries, and more.

## Next.js App Router

### Basic Setup

```tsx
// app/layout.tsx
import type { ReactNode } from 'react'
import { Provider } from '@/components/ui/provider'

interface RootLayoutProps {
  children: ReactNode
}

export default function RootLayout({ children }: RootLayoutProps): JSX.Element {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Provider>{children}</Provider>
      </body>
    </html>
  )
}
```

```tsx
// components/ui/provider.tsx
'use client'

import type { ReactNode } from 'react'
import { ChakraProvider, defaultSystem } from '@chakra-ui/react'

interface ProviderProps {
  children: ReactNode
}

export function Provider({ children }: ProviderProps): JSX.Element {
  return (
    <ChakraProvider value={defaultSystem}>
      {children}
    </ChakraProvider>
  )
}
```

### With Custom Theme

```tsx
// theme.ts
import { createSystem, defaultConfig, defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    tokens: {
      colors: {
        brand: {
          50: { value: '#e6f2ff' },
          500: { value: '#0073e6' },
          900: { value: '#00161a' },
        },
      },
    },
    semanticTokens: {
      colors: {
        brand: {
          solid: { value: '{colors.brand.500}' },
          contrast: { value: 'white' },
          fg: { value: '{colors.brand.900}' },
        },
      },
    },
  },
})

export const system = createSystem(defaultConfig, config)
```

```tsx
// components/ui/provider.tsx
'use client'

import type { ReactNode } from 'react'
import { ChakraProvider } from '@chakra-ui/react'
import { system } from '@/theme'

export function Provider({ children }: { children: ReactNode }) {
  return <ChakraProvider value={system}>{children}</ChakraProvider>
}
```

### Font Loading with next/font

```tsx
// app/layout.tsx
import { Inter } from 'next/font/google'
import { Provider } from '@/components/ui/provider'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
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
        heading: { value: 'var(--font-inter), system-ui, sans-serif' },
        body: { value: 'var(--font-inter), system-ui, sans-serif' },
      },
    },
  },
})
```

### Server Components

```tsx
// Chakra components must be used in Client Components
// Mark files with 'use client' directive

// app/page.tsx (Server Component - cannot use Chakra directly)
import { ClientSection } from './client-section'

export default function Page() {
  // Fetch data on server
  const data = await fetchData()

  return (
    <main>
      <h1>Server-rendered title</h1>
      <ClientSection data={data} />
    </main>
  )
}

// app/client-section.tsx (Client Component)
'use client'

import { Box, Card, Text } from '@chakra-ui/react'

interface ClientSectionProps {
  data: SomeDataType
}

export function ClientSection({ data }: ClientSectionProps) {
  return (
    <Box p="4">
      <Card.Root>
        <Card.Body>
          <Text>{data.content}</Text>
        </Card.Body>
      </Card.Root>
    </Box>
  )
}
```

### Metadata and SEO

```tsx
// app/layout.tsx
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'My App',
  description: 'Built with Next.js and Chakra UI',
}

// Color mode meta tag
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="color-scheme" content="light dark" />
      </head>
      <body>
        <Provider>{children}</Provider>
      </body>
    </html>
  )
}
```

## React Hook Form

### Basic Integration

```tsx
'use client'

import type { FC } from 'react'
import { useForm } from 'react-hook-form'
import { Button, Field, Input, Stack, Textarea } from '@chakra-ui/react'

interface ContactFormData {
  name: string
  email: string
  message: string
}

export const ContactForm: FC = () => {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<ContactFormData>()

  const onSubmit = async (data: ContactFormData): Promise<void> => {
    await fetch('/api/contact', {
      method: 'POST',
      body: JSON.stringify(data),
    })
    reset()
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <Stack gap="4">
        <Field.Root invalid={!!errors.name}>
          <Field.Label>Name</Field.Label>
          <Input
            {...register('name', { required: 'Name is required' })}
          />
          {errors.name && (
            <Field.ErrorText>{errors.name.message}</Field.ErrorText>
          )}
        </Field.Root>

        <Field.Root invalid={!!errors.email}>
          <Field.Label>Email</Field.Label>
          <Input
            type="email"
            {...register('email', {
              required: 'Email is required',
              pattern: {
                value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                message: 'Invalid email address',
              },
            })}
          />
          {errors.email && (
            <Field.ErrorText>{errors.email.message}</Field.ErrorText>
          )}
        </Field.Root>

        <Field.Root invalid={!!errors.message}>
          <Field.Label>Message</Field.Label>
          <Textarea
            {...register('message', {
              required: 'Message is required',
              minLength: {
                value: 10,
                message: 'Message must be at least 10 characters',
              },
            })}
          />
          {errors.message && (
            <Field.ErrorText>{errors.message.message}</Field.ErrorText>
          )}
        </Field.Root>

        <Button type="submit" colorPalette="blue" loading={isSubmitting}>
          Send Message
        </Button>
      </Stack>
    </form>
  )
}
```

### With Zod Validation

```tsx
'use client'

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button, Field, Input, Stack } from '@chakra-ui/react'

const loginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain uppercase letter')
    .regex(/[0-9]/, 'Password must contain a number'),
})

type LoginFormData = z.infer<typeof loginSchema>

export function LoginForm() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginFormData) => {
    // Handle login
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <Stack gap="4">
        <Field.Root invalid={!!errors.email}>
          <Field.Label>Email</Field.Label>
          <Input type="email" {...register('email')} />
          {errors.email && (
            <Field.ErrorText>{errors.email.message}</Field.ErrorText>
          )}
        </Field.Root>

        <Field.Root invalid={!!errors.password}>
          <Field.Label>Password</Field.Label>
          <Input type="password" {...register('password')} />
          {errors.password && (
            <Field.ErrorText>{errors.password.message}</Field.ErrorText>
          )}
        </Field.Root>

        <Button type="submit" colorPalette="blue" loading={isSubmitting}>
          Sign In
        </Button>
      </Stack>
    </form>
  )
}
```

### Custom Form Components

```tsx
import type { FC } from 'react'
import { useController, Control } from 'react-hook-form'
import { Field, Input, Select, Portal } from '@chakra-ui/react'

interface FormInputProps {
  name: string
  control: Control<any>
  label: string
  type?: string
  placeholder?: string
}

export const FormInput: FC<FormInputProps> = ({
  name,
  control,
  label,
  type = 'text',
  placeholder,
}) => {
  const {
    field,
    fieldState: { error },
  } = useController({ name, control })

  return (
    <Field.Root invalid={!!error}>
      <Field.Label>{label}</Field.Label>
      <Input
        {...field}
        type={type}
        placeholder={placeholder}
      />
      {error && <Field.ErrorText>{error.message}</Field.ErrorText>}
    </Field.Root>
  )
}

interface FormSelectProps {
  name: string
  control: Control<any>
  label: string
  options: { value: string; label: string }[]
  placeholder?: string
}

export const FormSelect: FC<FormSelectProps> = ({
  name,
  control,
  label,
  options,
  placeholder,
}) => {
  const {
    field,
    fieldState: { error },
  } = useController({ name, control })

  return (
    <Field.Root invalid={!!error}>
      <Field.Label>{label}</Field.Label>
      <Select.Root
        value={[field.value]}
        onValueChange={(details) => field.onChange(details.value[0])}
      >
        <Select.Trigger>
          <Select.ValueText placeholder={placeholder} />
        </Select.Trigger>
        <Portal>
          <Select.Positioner>
            <Select.Content>
              {options.map((option) => (
                <Select.Item key={option.value} item={option.value}>
                  <Select.ItemText>{option.label}</Select.ItemText>
                  <Select.ItemIndicator />
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Positioner>
        </Portal>
      </Select.Root>
      {error && <Field.ErrorText>{error.message}</Field.ErrorText>}
    </Field.Root>
  )
}
```

## TanStack Query

### With Data Fetching

```tsx
'use client'

import type { FC } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Button,
  Card,
  Skeleton,
  Stack,
  Text,
  toaster,
} from '@chakra-ui/react'

interface User {
  id: string
  name: string
  email: string
}

const fetchUsers = async (): Promise<User[]> => {
  const res = await fetch('/api/users')
  if (!res.ok) throw new Error('Failed to fetch')
  return res.json()
}

const deleteUser = async (id: string): Promise<void> => {
  const res = await fetch(`/api/users/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete')
}

export const UserList: FC = () => {
  const queryClient = useQueryClient()

  const { data: users, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: fetchUsers,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toaster.create({
        title: 'User deleted',
        type: 'success',
      })
    },
    onError: () => {
      toaster.create({
        title: 'Failed to delete user',
        type: 'error',
      })
    },
  })

  if (isLoading) {
    return (
      <Stack gap="4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} height="100px" />
        ))}
      </Stack>
    )
  }

  if (error) {
    return (
      <Box p="4" bg="error.subtle" color="error.fg" rounded="lg">
        Error loading users
      </Box>
    )
  }

  return (
    <Stack gap="4">
      {users?.map((user) => (
        <Card.Root key={user.id}>
          <Card.Body>
            <Text fontWeight="bold">{user.name}</Text>
            <Text color="fg.muted">{user.email}</Text>
          </Card.Body>
          <Card.Footer>
            <Button
              size="sm"
              colorPalette="red"
              variant="outline"
              loading={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(user.id)}
            >
              Delete
            </Button>
          </Card.Footer>
        </Card.Root>
      ))}
    </Stack>
  )
}
```

## TypeScript Patterns

### Typed Theme Tokens

```tsx
// theme.ts
import { createSystem, defaultConfig, defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    tokens: {
      colors: {
        brand: {
          50: { value: '#e6f2ff' },
          500: { value: '#0073e6' },
          900: { value: '#00161a' },
        },
      },
      spacing: {
        section: { value: '4rem' },
      },
    },
  },
})

export const system = createSystem(defaultConfig, config)
export type AppTheme = typeof config.theme
```

```tsx
// chakra.d.ts - Augment Chakra types
import { config } from './theme'

type Config = typeof config

declare module '@chakra-ui/react' {
  export interface SystemConfig extends Config {}
}
```

### Typed Component Props

```tsx
import type { FC, ReactNode } from 'react'
import type { BoxProps, ButtonProps, SystemStyleObject } from '@chakra-ui/react'
import { Box, Button } from '@chakra-ui/react'

// Extend Box props
interface CardProps extends BoxProps {
  variant?: 'elevated' | 'outline' | 'filled'
}

export const Card: FC<CardProps> = ({ variant = 'elevated', ...props }) => {
  const variants: Record<string, SystemStyleObject> = {
    elevated: { shadow: 'lg', bg: 'bg' },
    outline: { borderWidth: '1px', borderColor: 'border' },
    filled: { bg: 'bg.muted' },
  }

  return <Box rounded="xl" p="4" {...variants[variant]} {...props} />
}

// Polymorphic component
interface PolymorphicProps<T extends React.ElementType> {
  as?: T
  children: ReactNode
}

type Props<T extends React.ElementType> = PolymorphicProps<T> &
  Omit<React.ComponentPropsWithoutRef<T>, keyof PolymorphicProps<T>>

export function PolymorphicBox<T extends React.ElementType = 'div'>({
  as,
  children,
  ...props
}: Props<T>) {
  const Component = as || 'div'
  return <Component {...props}>{children}</Component>
}
```

### Recipe Type Safety

```tsx
import { defineRecipe } from '@chakra-ui/react'
import type { RecipeVariantProps } from '@chakra-ui/react'

export const buttonRecipe = defineRecipe({
  base: {
    display: 'inline-flex',
    alignItems: 'center',
  },
  variants: {
    variant: {
      solid: { bg: 'brand.solid', color: 'brand.contrast' },
      outline: { borderWidth: '1px', borderColor: 'brand.solid' },
      ghost: { bg: 'transparent' },
    },
    size: {
      sm: { h: '8', px: '3', fontSize: 'sm' },
      md: { h: '10', px: '4', fontSize: 'md' },
      lg: { h: '12', px: '6', fontSize: 'lg' },
    },
  },
  defaultVariants: {
    variant: 'solid',
    size: 'md',
  },
})

// Extract variant types
export type ButtonVariants = RecipeVariantProps<typeof buttonRecipe>

// Use in component
interface CustomButtonProps extends ButtonVariants {
  children: ReactNode
  onClick?: () => void
  loading?: boolean
}

export const CustomButton: FC<CustomButtonProps> = ({
  variant,
  size,
  children,
  ...props
}) => {
  // variant and size are properly typed
  return <button className={buttonRecipe({ variant, size })} {...props}>{children}</button>
}
```

## React Router

### With React Router v6

```tsx
import type { FC } from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'
import { Box, Link, HStack } from '@chakra-ui/react'

interface NavLinkProps {
  to: string
  children: React.ReactNode
}

const NavLink: FC<NavLinkProps> = ({ to, children }) => {
  const location = useLocation()
  const isActive = location.pathname === to

  return (
    <Link
      as={RouterLink}
      to={to}
      px="3"
      py="2"
      rounded="md"
      bg={isActive ? 'brand.subtle' : 'transparent'}
      color={isActive ? 'brand.fg' : 'fg'}
      fontWeight={isActive ? 'medium' : 'normal'}
      _hover={{ bg: 'bg.subtle' }}
    >
      {children}
    </Link>
  )
}

export const Navigation: FC = () => {
  return (
    <Box as="nav" p="4" borderBottomWidth="1px">
      <HStack gap="2">
        <NavLink to="/">Home</NavLink>
        <NavLink to="/about">About</NavLink>
        <NavLink to="/contact">Contact</NavLink>
      </HStack>
    </Box>
  )
}
```

## Icons

### With Lucide React

```tsx
import type { FC } from 'react'
import { LuHome, LuUser, LuSettings, LuSearch } from 'react-icons/lu'
import { Button, Input, HStack, IconButton } from '@chakra-ui/react'

// In buttons
export const IconButtonExample: FC = () => (
  <HStack>
    <Button>
      <LuHome />
      Home
    </Button>

    <IconButton aria-label="Settings">
      <LuSettings />
    </IconButton>
  </HStack>
)

// In inputs
export const SearchInput: FC = () => (
  <HStack>
    <LuSearch />
    <Input placeholder="Search..." />
  </HStack>
)
```

### With Custom Icon Component

```tsx
import type { FC, SVGProps } from 'react'
import { Box } from '@chakra-ui/react'

interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number | string
  color?: string
}

export const Icon: FC<IconProps> = ({
  size = '1em',
  color = 'currentColor',
  children,
  ...props
}) => {
  return (
    <Box
      as="svg"
      width={size}
      height={size}
      color={color}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      viewBox="0 0 24 24"
      {...props}
    >
      {children}
    </Box>
  )
}

// Custom icon
export const CustomCheckIcon: FC<Omit<IconProps, 'children'>> = (props) => (
  <Icon {...props}>
    <polyline points="20 6 9 17 4 12" />
  </Icon>
)
```

## Framer Motion (Optional)

```tsx
'use client'

import type { FC, ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Box } from '@chakra-ui/react'

// Create motion components
const MotionBox = motion(Box)

interface FadeInProps {
  children: ReactNode
}

export const FadeIn: FC<FadeInProps> = ({ children }) => (
  <MotionBox
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.3 }}
  >
    {children}
  </MotionBox>
)

// Page transitions
interface PageTransitionProps {
  children: ReactNode
}

export const PageTransition: FC<PageTransitionProps> = ({ children }) => (
  <AnimatePresence mode="wait">
    <MotionBox
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      {children}
    </MotionBox>
  </AnimatePresence>
)
```

## Testing

### With React Testing Library

```tsx
// test-utils.tsx
import type { FC, ReactNode } from 'react'
import { render, RenderOptions } from '@testing-library/react'
import { ChakraProvider, defaultSystem } from '@chakra-ui/react'

const AllProviders: FC<{ children: ReactNode }> = ({ children }) => {
  return <ChakraProvider value={defaultSystem}>{children}</ChakraProvider>
}

const customRender = (ui: React.ReactElement, options?: RenderOptions) =>
  render(ui, { wrapper: AllProviders, ...options })

export * from '@testing-library/react'
export { customRender as render }
```

```tsx
// Button.test.tsx
import { render, screen, fireEvent } from './test-utils'
import { Button } from '@chakra-ui/react'

describe('Button', () => {
  it('renders correctly', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole('button')).toHaveTextContent('Click me')
  })

  it('handles click events', () => {
    const handleClick = vi.fn()
    render(<Button onClick={handleClick}>Click me</Button>)

    fireEvent.click(screen.getByRole('button'))
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('shows loading state', () => {
    render(<Button loading>Submit</Button>)
    expect(screen.getByRole('button')).toHaveAttribute('data-loading')
  })
})
```
