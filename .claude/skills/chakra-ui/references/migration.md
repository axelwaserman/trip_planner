# Chakra UI Migration Guide (v2 to v3)

Complete guide for migrating from Chakra UI v2 to v3.

## Overview

Chakra UI v3 is a major rewrite with significant breaking changes:

- **Compound components** - Dot notation replaces flat imports
- **New theming system** - `createSystem` replaces `extendTheme`
- **Recipes** - Replace component style props
- **Ark UI foundation** - Headless primitives from Ark UI
- **No more color mode provider** - Built into ChakraProvider

## Quick Migration Checklist

- [ ] Update dependencies
- [ ] Replace `ChakraProvider` setup
- [ ] Convert flat components to compound components
- [ ] Migrate theme from `extendTheme` to `createSystem`
- [ ] Update color mode implementation
- [ ] Replace deprecated components
- [ ] Update style props (some renamed)

## Dependency Changes

```bash
# Remove v2 dependencies
npm uninstall @chakra-ui/react @chakra-ui/icons @emotion/react @emotion/styled framer-motion

# Install v3 dependencies
npm install @chakra-ui/react @emotion/react

# Icons are now separate (optional)
npm install react-icons
```

**Key changes:**
- `framer-motion` no longer required
- `@emotion/styled` no longer required
- `@chakra-ui/icons` deprecated - use `react-icons` or `lucide-react`

## Provider Setup

### v2 (Old)

```tsx
import { ChakraProvider, extendTheme } from '@chakra-ui/react'

const theme = extendTheme({
  colors: {
    brand: {
      500: '#0073e6',
    },
  },
})

function App({ children }) {
  return <ChakraProvider theme={theme}>{children}</ChakraProvider>
}
```

### v3 (New)

```tsx
import { ChakraProvider, createSystem, defaultConfig, defineConfig } from '@chakra-ui/react'

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

const system = createSystem(defaultConfig, config)

function App({ children }: { children: React.ReactNode }) {
  return <ChakraProvider value={system}>{children}</ChakraProvider>
}
```

## Component Migration

### Modal → Dialog

```tsx
// v2 (Old)
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
} from '@chakra-ui/react'

<Modal isOpen={isOpen} onClose={onClose}>
  <ModalOverlay />
  <ModalContent>
    <ModalHeader>Title</ModalHeader>
    <ModalCloseButton />
    <ModalBody>Content</ModalBody>
    <ModalFooter>
      <Button onClick={onClose}>Close</Button>
    </ModalFooter>
  </ModalContent>
</Modal>

// v3 (New)
import { Dialog, Portal } from '@chakra-ui/react'

<Dialog.Root open={open} onOpenChange={(e) => setOpen(e.open)}>
  <Dialog.Trigger asChild>
    <Button>Open</Button>
  </Dialog.Trigger>
  <Portal>
    <Dialog.Backdrop />
    <Dialog.Positioner>
      <Dialog.Content>
        <Dialog.Header>
          <Dialog.Title>Title</Dialog.Title>
        </Dialog.Header>
        <Dialog.Body>Content</Dialog.Body>
        <Dialog.Footer>
          <Dialog.CloseTrigger asChild>
            <Button>Close</Button>
          </Dialog.CloseTrigger>
        </Dialog.Footer>
        <Dialog.CloseTrigger />
      </Dialog.Content>
    </Dialog.Positioner>
  </Portal>
</Dialog.Root>
```

### Menu

```tsx
// v2 (Old)
import { Menu, MenuButton, MenuList, MenuItem } from '@chakra-ui/react'

<Menu>
  <MenuButton as={Button}>Actions</MenuButton>
  <MenuList>
    <MenuItem>Edit</MenuItem>
    <MenuItem>Delete</MenuItem>
  </MenuList>
</Menu>

// v3 (New)
import { Menu, Portal } from '@chakra-ui/react'

<Menu.Root>
  <Menu.Trigger asChild>
    <Button>Actions</Button>
  </Menu.Trigger>
  <Portal>
    <Menu.Positioner>
      <Menu.Content>
        <Menu.Item value="edit">Edit</Menu.Item>
        <Menu.Item value="delete">Delete</Menu.Item>
      </Menu.Content>
    </Menu.Positioner>
  </Portal>
</Menu.Root>
```

### Tabs

```tsx
// v2 (Old)
import { Tabs, TabList, Tab, TabPanels, TabPanel } from '@chakra-ui/react'

<Tabs>
  <TabList>
    <Tab>One</Tab>
    <Tab>Two</Tab>
  </TabList>
  <TabPanels>
    <TabPanel>Content 1</TabPanel>
    <TabPanel>Content 2</TabPanel>
  </TabPanels>
</Tabs>

// v3 (New)
import { Tabs } from '@chakra-ui/react'

<Tabs.Root defaultValue="one">
  <Tabs.List>
    <Tabs.Trigger value="one">One</Tabs.Trigger>
    <Tabs.Trigger value="two">Two</Tabs.Trigger>
  </Tabs.List>
  <Tabs.Content value="one">Content 1</Tabs.Content>
  <Tabs.Content value="two">Content 2</Tabs.Content>
</Tabs.Root>
```

### Accordion

```tsx
// v2 (Old)
import {
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
} from '@chakra-ui/react'

<Accordion>
  <AccordionItem>
    <AccordionButton>
      Section 1
      <AccordionIcon />
    </AccordionButton>
    <AccordionPanel>Content 1</AccordionPanel>
  </AccordionItem>
</Accordion>

// v3 (New)
import { Accordion } from '@chakra-ui/react'

<Accordion.Root>
  <Accordion.Item value="item-1">
    <Accordion.ItemTrigger>
      Section 1
      <Accordion.ItemIndicator />
    </Accordion.ItemTrigger>
    <Accordion.ItemContent>Content 1</Accordion.ItemContent>
  </Accordion.Item>
</Accordion.Root>
```

### Form Controls

```tsx
// v2 (Old)
import { FormControl, FormLabel, FormErrorMessage, Input } from '@chakra-ui/react'

<FormControl isInvalid={!!error}>
  <FormLabel>Email</FormLabel>
  <Input type="email" />
  <FormErrorMessage>{error}</FormErrorMessage>
</FormControl>

// v3 (New)
import { Field, Input } from '@chakra-ui/react'

<Field.Root invalid={!!error}>
  <Field.Label>Email</Field.Label>
  <Input type="email" />
  <Field.ErrorText>{error}</Field.ErrorText>
</Field.Root>
```

### Checkbox

```tsx
// v2 (Old)
import { Checkbox, CheckboxGroup } from '@chakra-ui/react'

<CheckboxGroup>
  <Checkbox value="one">One</Checkbox>
  <Checkbox value="two">Two</Checkbox>
</CheckboxGroup>

// v3 (New)
import { Checkbox } from '@chakra-ui/react'

<Checkbox.Group>
  <Checkbox.Root value="one">
    <Checkbox.HiddenInput />
    <Checkbox.Control>
      <Checkbox.Indicator />
    </Checkbox.Control>
    <Checkbox.Label>One</Checkbox.Label>
  </Checkbox.Root>
  <Checkbox.Root value="two">
    <Checkbox.HiddenInput />
    <Checkbox.Control>
      <Checkbox.Indicator />
    </Checkbox.Control>
    <Checkbox.Label>Two</Checkbox.Label>
  </Checkbox.Root>
</Checkbox.Group>
```

### Radio

```tsx
// v2 (Old)
import { Radio, RadioGroup } from '@chakra-ui/react'

<RadioGroup value={value} onChange={setValue}>
  <Radio value="1">Option 1</Radio>
  <Radio value="2">Option 2</Radio>
</RadioGroup>

// v3 (New)
import { RadioGroup } from '@chakra-ui/react'

<RadioGroup.Root value={value} onValueChange={(d) => setValue(d.value)}>
  <RadioGroup.Item value="1">
    <RadioGroup.ItemHiddenInput />
    <RadioGroup.ItemControl />
    <RadioGroup.ItemText>Option 1</RadioGroup.ItemText>
  </RadioGroup.Item>
  <RadioGroup.Item value="2">
    <RadioGroup.ItemHiddenInput />
    <RadioGroup.ItemControl />
    <RadioGroup.ItemText>Option 2</RadioGroup.ItemText>
  </RadioGroup.Item>
</RadioGroup.Root>
```

### Switch

```tsx
// v2 (Old)
import { Switch } from '@chakra-ui/react'

<Switch isChecked={checked} onChange={(e) => setChecked(e.target.checked)}>
  Enable
</Switch>

// v3 (New)
import { Switch } from '@chakra-ui/react'

<Switch.Root checked={checked} onCheckedChange={(d) => setChecked(d.checked)}>
  <Switch.HiddenInput />
  <Switch.Control>
    <Switch.Thumb />
  </Switch.Control>
  <Switch.Label>Enable</Switch.Label>
</Switch.Root>
```

### Tooltip

```tsx
// v2 (Old)
import { Tooltip } from '@chakra-ui/react'

<Tooltip label="Tooltip text">
  <Button>Hover me</Button>
</Tooltip>

// v3 (New)
import { Tooltip } from '@chakra-ui/react'

<Tooltip.Root>
  <Tooltip.Trigger asChild>
    <Button>Hover me</Button>
  </Tooltip.Trigger>
  <Tooltip.Positioner>
    <Tooltip.Content>
      <Tooltip.Arrow>
        <Tooltip.ArrowTip />
      </Tooltip.Arrow>
      Tooltip text
    </Tooltip.Content>
  </Tooltip.Positioner>
</Tooltip.Root>
```

### Popover

```tsx
// v2 (Old)
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverHeader,
  PopoverBody,
  PopoverArrow,
  PopoverCloseButton,
} from '@chakra-ui/react'

<Popover>
  <PopoverTrigger>
    <Button>Click</Button>
  </PopoverTrigger>
  <PopoverContent>
    <PopoverArrow />
    <PopoverCloseButton />
    <PopoverHeader>Title</PopoverHeader>
    <PopoverBody>Content</PopoverBody>
  </PopoverContent>
</Popover>

// v3 (New)
import { Popover, Portal } from '@chakra-ui/react'

<Popover.Root>
  <Popover.Trigger asChild>
    <Button>Click</Button>
  </Popover.Trigger>
  <Portal>
    <Popover.Positioner>
      <Popover.Content>
        <Popover.Arrow>
          <Popover.ArrowTip />
        </Popover.Arrow>
        <Popover.Header>
          <Popover.Title>Title</Popover.Title>
        </Popover.Header>
        <Popover.Body>Content</Popover.Body>
        <Popover.CloseTrigger />
      </Popover.Content>
    </Popover.Positioner>
  </Portal>
</Popover.Root>
```

### Drawer

```tsx
// v2 (Old)
import {
  Drawer,
  DrawerOverlay,
  DrawerContent,
  DrawerHeader,
  DrawerBody,
  DrawerCloseButton,
} from '@chakra-ui/react'

<Drawer isOpen={isOpen} onClose={onClose} placement="right">
  <DrawerOverlay />
  <DrawerContent>
    <DrawerCloseButton />
    <DrawerHeader>Title</DrawerHeader>
    <DrawerBody>Content</DrawerBody>
  </DrawerContent>
</Drawer>

// v3 (New)
import { Drawer, Portal } from '@chakra-ui/react'

<Drawer.Root open={open} onOpenChange={(e) => setOpen(e.open)} placement="right">
  <Portal>
    <Drawer.Backdrop />
    <Drawer.Positioner>
      <Drawer.Content>
        <Drawer.Header>
          <Drawer.Title>Title</Drawer.Title>
        </Drawer.Header>
        <Drawer.Body>Content</Drawer.Body>
        <Drawer.CloseTrigger />
      </Drawer.Content>
    </Drawer.Positioner>
  </Portal>
</Drawer.Root>
```

### Progress

```tsx
// v2 (Old)
import { Progress } from '@chakra-ui/react'

<Progress value={60} />
<Progress isIndeterminate />

// v3 (New)
import { Progress } from '@chakra-ui/react'

<Progress.Root value={60}>
  <Progress.Track>
    <Progress.Range />
  </Progress.Track>
</Progress.Root>

<Progress.Root value={null}>
  <Progress.Track>
    <Progress.Range />
  </Progress.Track>
</Progress.Root>
```

### Alert

```tsx
// v2 (Old)
import { Alert, AlertIcon, AlertTitle, AlertDescription } from '@chakra-ui/react'

<Alert status="error">
  <AlertIcon />
  <AlertTitle>Error!</AlertTitle>
  <AlertDescription>Something went wrong.</AlertDescription>
</Alert>

// v3 (New)
import { Alert } from '@chakra-ui/react'

<Alert.Root status="error">
  <Alert.Indicator />
  <Alert.Content>
    <Alert.Title>Error!</Alert.Title>
    <Alert.Description>Something went wrong.</Alert.Description>
  </Alert.Content>
</Alert.Root>
```

## Theming Migration

### Token Structure

```tsx
// v2 (Old)
const theme = extendTheme({
  colors: {
    brand: {
      500: '#0073e6',
    },
  },
  fonts: {
    heading: 'Inter',
    body: 'Inter',
  },
  space: {
    xs: '0.25rem',
  },
})

// v3 (New)
const config = defineConfig({
  theme: {
    tokens: {
      colors: {
        brand: {
          500: { value: '#0073e6' },  // Note: { value: } wrapper
        },
      },
      fonts: {
        heading: { value: 'Inter, sans-serif' },
        body: { value: 'Inter, sans-serif' },
      },
      spacing: {  // Note: "space" renamed to "spacing"
        xs: { value: '0.25rem' },
      },
    },
  },
})
```

### Component Styles → Recipes

```tsx
// v2 (Old)
const theme = extendTheme({
  components: {
    Button: {
      baseStyle: {
        fontWeight: 'bold',
      },
      variants: {
        brand: {
          bg: 'brand.500',
          color: 'white',
        },
      },
    },
  },
})

// v3 (New)
import { defineRecipe } from '@chakra-ui/react'

const buttonRecipe = defineRecipe({
  base: {
    fontWeight: 'bold',
  },
  variants: {
    variant: {
      brand: {
        bg: 'brand.500',
        color: 'white',
      },
    },
  },
})

const config = defineConfig({
  theme: {
    recipes: {
      button: buttonRecipe,
    },
  },
})
```

### Global Styles

```tsx
// v2 (Old)
const theme = extendTheme({
  styles: {
    global: {
      body: {
        bg: 'gray.50',
      },
    },
  },
})

// v3 (New)
const config = defineConfig({
  globalCss: {
    body: {
      bg: 'gray.50',
    },
  },
})
```

## Color Mode Migration

### v2 (Old)

```tsx
import { ColorModeScript, useColorMode, useColorModeValue } from '@chakra-ui/react'

// In _document.tsx or index.html
<ColorModeScript initialColorMode="system" />

// In components
function Component() {
  const { colorMode, toggleColorMode } = useColorMode()
  const bg = useColorModeValue('white', 'gray.800')

  return <Box bg={bg}>...</Box>
}
```

### v3 (New)

```tsx
import { useColorMode } from '@chakra-ui/react'

// No ColorModeScript needed - handled by ChakraProvider

// In components
function Component() {
  const { colorMode, toggleColorMode } = useColorMode()

  // Use semantic tokens instead of useColorModeValue
  return <Box bg="bg">...</Box>  // "bg" token auto-switches
}

// Semantic tokens handle light/dark automatically
const config = defineConfig({
  theme: {
    semanticTokens: {
      colors: {
        bg: {
          value: { base: 'white', _dark: '{colors.gray.800}' },
        },
      },
    },
  },
})
```

## Prop Renames

| v2 Prop | v3 Prop | Component |
|---------|---------|-----------|
| `isOpen` | `open` | Dialog, Drawer, Menu, Popover |
| `onClose` | `onOpenChange` | Dialog, Drawer, Menu, Popover |
| `isChecked` | `checked` | Checkbox, Switch |
| `isDisabled` | `disabled` | Button, Input, etc. |
| `isInvalid` | `invalid` | Field |
| `isRequired` | `required` | Field |
| `isLoading` | `loading` | Button |
| `colorScheme` | `colorPalette` | Button, Badge, etc. |
| `spacing` | `gap` | Stack, Flex, Grid |

## Removed Components

| v2 Component | v3 Alternative |
|--------------|----------------|
| `Wrap` | Use `Flex` with `wrap="wrap"` |
| `WrapItem` | Children of Flex |
| `SimpleGrid` | Use `Grid` with `templateColumns` |
| `InputLeftElement` | Use `InputGroup` pattern |
| `InputRightElement` | Use `InputGroup` pattern |
| `FormControl` | `Field.Root` |
| `FormLabel` | `Field.Label` |
| `FormErrorMessage` | `Field.ErrorText` |
| `FormHelperText` | `Field.HelperText` |

## Hook Changes

```tsx
// v2 - useDisclosure
const { isOpen, onOpen, onClose } = useDisclosure()

// v3 - useState (useDisclosure still works but less common)
const [open, setOpen] = useState(false)

// v2 - useColorModeValue
const bg = useColorModeValue('white', 'gray.800')

// v3 - Semantic tokens (preferred)
<Box bg="bg" />  // Token handles light/dark

// v2 - useBreakpointValue
const size = useBreakpointValue({ base: 'sm', md: 'lg' })

// v3 - Still available, but responsive props preferred
<Button size={{ base: 'sm', md: 'lg' }} />
```

## Migration Tips

1. **Start with Provider** - Update the ChakraProvider setup first
2. **Use CLI snippets** - Run `npx @chakra-ui/cli snippet add` for pre-built components
3. **Migrate one component at a time** - Don't try to convert everything at once
4. **Use semantic tokens** - Replace `useColorModeValue` with semantic tokens
5. **Check console warnings** - v3 provides helpful migration warnings
6. **Test thoroughly** - Especially modals, menus, and other overlay components
7. **Update tests** - Component structure changes may break existing tests

## Codemods

The Chakra team provides codemods to help automate some migrations:

```bash
npx @chakra-ui/codemod <transform> <path>
```

Available transforms:
- `update-imports` - Updates import paths
- `rename-props` - Renames deprecated props

Check the official documentation for the latest codemods.
