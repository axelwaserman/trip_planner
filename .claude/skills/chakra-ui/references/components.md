# Chakra UI Components Reference

Complete component API for Chakra UI v3 with TypeScript.

## Data Display

### Avatar

```tsx
import type { FC } from 'react'
import { Avatar, AvatarGroup } from '@chakra-ui/react'

interface User {
  id: string
  name: string
  imageUrl?: string
}

interface AvatarListProps {
  users: User[]
  max?: number
}

const AvatarList: FC<AvatarListProps> = ({ users, max = 3 }) => {
  const getInitials = (name: string): string => {
    return name.split(' ').map(n => n[0]).join('').toUpperCase()
  }

  return (
    <AvatarGroup max={max}>
      {users.map((user) => (
        <Avatar.Root key={user.id} size="lg">
          <Avatar.Image src={user.imageUrl} alt={user.name} />
          <Avatar.Fallback>{getInitials(user.name)}</Avatar.Fallback>
        </Avatar.Root>
      ))}
    </AvatarGroup>
  )
}
```

### Badge

```tsx
import type { FC } from 'react'
import { Badge } from '@chakra-ui/react'

type BadgeVariant = 'solid' | 'outline' | 'subtle'
type BadgeStatus = 'default' | 'success' | 'error' | 'warning' | 'info'

interface StatusBadgeProps {
  status: BadgeStatus
  variant?: BadgeVariant
  children: React.ReactNode
}

const statusColorMap: Record<BadgeStatus, string> = {
  default: 'gray',
  success: 'green',
  error: 'red',
  warning: 'orange',
  info: 'blue',
}

const StatusBadge: FC<StatusBadgeProps> = ({ status, variant = 'subtle', children }) => {
  return (
    <Badge colorPalette={statusColorMap[status]} variant={variant}>
      {children}
    </Badge>
  )
}
```

### Table

```tsx
import type { FC } from 'react'
import { Table } from '@chakra-ui/react'

interface Column<T> {
  key: keyof T
  header: string
  numeric?: boolean
}

interface DataTableProps<T extends { id: string }> {
  data: T[]
  columns: Column<T>[]
}

function DataTable<T extends { id: string }>({ data, columns }: DataTableProps<T>): JSX.Element {
  return (
    <Table.Root>
      <Table.Header>
        <Table.Row>
          {columns.map((col) => (
            <Table.ColumnHeader key={String(col.key)} numeric={col.numeric}>
              {col.header}
            </Table.ColumnHeader>
          ))}
        </Table.Row>
      </Table.Header>
      <Table.Body>
        {data.map((item) => (
          <Table.Row key={item.id}>
            {columns.map((col) => (
              <Table.Cell key={String(col.key)} numeric={col.numeric}>
                {String(item[col.key])}
              </Table.Cell>
            ))}
          </Table.Row>
        ))}
      </Table.Body>
    </Table.Root>
  )
}
```

### Stat

```tsx
import type { FC } from 'react'
import { Stat } from '@chakra-ui/react'

interface StatCardProps {
  label: string
  value: string | number
  change?: number
  helpText?: string
}

const StatCard: FC<StatCardProps> = ({ label, value, change, helpText }) => {
  return (
    <Stat.Root>
      <Stat.Label>{label}</Stat.Label>
      <Stat.ValueText>{value}</Stat.ValueText>
      {change !== undefined && (
        <Stat.HelpText>
          {change >= 0 ? <Stat.UpIndicator /> : <Stat.DownIndicator />}
          {Math.abs(change)}%
        </Stat.HelpText>
      )}
      {helpText && <Stat.HelpText>{helpText}</Stat.HelpText>}
    </Stat.Root>
  )
}
```

### Tag

```tsx
import type { FC } from 'react'
import { Tag } from '@chakra-ui/react'

interface TagListProps {
  tags: string[]
  colorPalette?: string
  onRemove?: (tag: string) => void
}

const TagList: FC<TagListProps> = ({ tags, colorPalette = 'blue', onRemove }) => {
  return (
    <>
      {tags.map((tag) => (
        <Tag.Root key={tag} colorPalette={colorPalette}>
          <Tag.Label>{tag}</Tag.Label>
          {onRemove && (
            <Tag.CloseTrigger onClick={() => onRemove(tag)} />
          )}
        </Tag.Root>
      ))}
    </>
  )
}
```

## Feedback

### Alert

```tsx
import type { FC } from 'react'
import { Alert } from '@chakra-ui/react'

type AlertStatus = 'info' | 'warning' | 'success' | 'error'

interface AlertBannerProps {
  status: AlertStatus
  title: string
  description?: string
}

const AlertBanner: FC<AlertBannerProps> = ({ status, title, description }) => {
  return (
    <Alert.Root status={status}>
      <Alert.Indicator />
      <Alert.Content>
        <Alert.Title>{title}</Alert.Title>
        {description && <Alert.Description>{description}</Alert.Description>}
      </Alert.Content>
    </Alert.Root>
  )
}
```

### Toast

```tsx
import type { FC } from 'react'
import { Toaster, toaster } from '@chakra-ui/react'

// Add Toaster to app root once
const AppRoot: FC<{ children: React.ReactNode }> = ({ children }) => (
  <>
    {children}
    <Toaster />
  </>
)

// Toast utility functions
type ToastType = 'success' | 'error' | 'warning' | 'info'

interface ToastOptions {
  title: string
  description?: string
  duration?: number
  action?: {
    label: string
    onClick: () => void
  }
}

const showToast = (type: ToastType, options: ToastOptions): void => {
  toaster.create({
    type,
    title: options.title,
    description: options.description,
    duration: options.duration ?? 5000,
    action: options.action,
  })
}

// Usage examples
const notifySuccess = (): void => {
  showToast('success', {
    title: 'Saved!',
    description: 'Your changes have been saved.',
  })
}

const notifyWithUndo = (): void => {
  showToast('info', {
    title: 'File deleted',
    action: {
      label: 'Undo',
      onClick: () => console.log('Undo clicked'),
    },
  })
}
```

### Progress

```tsx
import type { FC } from 'react'
import { Progress } from '@chakra-ui/react'

interface ProgressBarProps {
  value: number | null
  showValue?: boolean
  colorPalette?: string
}

const ProgressBar: FC<ProgressBarProps> = ({ value, showValue = true, colorPalette = 'blue' }) => {
  return (
    <Progress.Root value={value} colorPalette={colorPalette}>
      <Progress.Track>
        <Progress.Range />
      </Progress.Track>
      {showValue && value !== null && (
        <Progress.ValueText>{value}%</Progress.ValueText>
      )}
    </Progress.Root>
  )
}
```

### Spinner

```tsx
import type { FC } from 'react'
import { Spinner, Center } from '@chakra-ui/react'

type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

interface LoadingSpinnerProps {
  size?: SpinnerSize
  colorPalette?: string
  fullScreen?: boolean
}

const LoadingSpinner: FC<LoadingSpinnerProps> = ({
  size = 'md',
  colorPalette = 'blue',
  fullScreen = false,
}) => {
  const spinner = <Spinner size={size} colorPalette={colorPalette} />

  if (fullScreen) {
    return <Center h="100vh">{spinner}</Center>
  }

  return spinner
}
```

### Skeleton

```tsx
import type { FC } from 'react'
import { Skeleton, SkeletonText, SkeletonCircle, Stack } from '@chakra-ui/react'

interface ContentSkeletonProps {
  isLoading: boolean
  children: React.ReactNode
}

const ContentSkeleton: FC<ContentSkeletonProps> = ({ isLoading, children }) => {
  if (isLoading) {
    return (
      <Stack gap="4">
        <SkeletonCircle size="12" />
        <Skeleton height="20px" width="200px" />
        <SkeletonText noOfLines={4} gap="4" />
      </Stack>
    )
  }

  return <>{children}</>
}

// Or use built-in loading prop
const InlineSkeleton: FC<ContentSkeletonProps> = ({ isLoading, children }) => {
  return <Skeleton loading={isLoading}>{children}</Skeleton>
}
```

## Form Components

### Checkbox

```tsx
import type { FC } from 'react'
import { Checkbox, Stack } from '@chakra-ui/react'

interface CheckboxOption {
  value: string
  label: string
}

interface CheckboxGroupProps {
  options: CheckboxOption[]
  value: string[]
  onChange: (value: string[]) => void
}

const CheckboxGroupExample: FC<CheckboxGroupProps> = ({ options, value, onChange }) => {
  return (
    <Checkbox.Group value={value} onValueChange={(details) => onChange(details.value)}>
      <Stack>
        {options.map((option) => (
          <Checkbox.Root key={option.value} value={option.value}>
            <Checkbox.HiddenInput />
            <Checkbox.Control>
              <Checkbox.Indicator />
            </Checkbox.Control>
            <Checkbox.Label>{option.label}</Checkbox.Label>
          </Checkbox.Root>
        ))}
      </Stack>
    </Checkbox.Group>
  )
}
```

### Radio

```tsx
import type { FC } from 'react'
import { RadioGroup, Stack } from '@chakra-ui/react'

interface RadioOption {
  value: string
  label: string
}

interface RadioGroupProps {
  options: RadioOption[]
  value: string
  onChange: (value: string) => void
}

const RadioGroupExample: FC<RadioGroupProps> = ({ options, value, onChange }) => {
  return (
    <RadioGroup.Root value={value} onValueChange={(details) => onChange(details.value)}>
      <Stack>
        {options.map((option) => (
          <RadioGroup.Item key={option.value} value={option.value}>
            <RadioGroup.ItemHiddenInput />
            <RadioGroup.ItemControl />
            <RadioGroup.ItemText>{option.label}</RadioGroup.ItemText>
          </RadioGroup.Item>
        ))}
      </Stack>
    </RadioGroup.Root>
  )
}
```

### Switch

```tsx
import type { FC } from 'react'
import { Switch } from '@chakra-ui/react'

interface ToggleSwitchProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
}

const ToggleSwitch: FC<ToggleSwitchProps> = ({ label, checked, onChange, disabled }) => {
  return (
    <Switch.Root
      checked={checked}
      onCheckedChange={(details) => onChange(details.checked)}
      disabled={disabled}
    >
      <Switch.HiddenInput />
      <Switch.Control>
        <Switch.Thumb />
      </Switch.Control>
      <Switch.Label>{label}</Switch.Label>
    </Switch.Root>
  )
}
```

### Slider

```tsx
import type { FC } from 'react'
import { Slider } from '@chakra-ui/react'

interface SliderInputProps {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
}

const SliderInput: FC<SliderInputProps> = ({ value, onChange, min = 0, max = 100, step = 1 }) => {
  return (
    <Slider.Root
      value={[value]}
      onValueChange={(details) => onChange(details.value[0])}
      min={min}
      max={max}
      step={step}
    >
      <Slider.Control>
        <Slider.Track>
          <Slider.Range />
        </Slider.Track>
        <Slider.Thumb index={0} />
      </Slider.Control>
    </Slider.Root>
  )
}

// Range slider
interface RangeSliderProps {
  value: [number, number]
  onChange: (value: [number, number]) => void
  min?: number
  max?: number
}

const RangeSlider: FC<RangeSliderProps> = ({ value, onChange, min = 0, max = 100 }) => {
  return (
    <Slider.Root
      value={value}
      onValueChange={(details) => onChange(details.value as [number, number])}
      min={min}
      max={max}
    >
      <Slider.Control>
        <Slider.Track>
          <Slider.Range />
        </Slider.Track>
        <Slider.Thumb index={0} />
        <Slider.Thumb index={1} />
      </Slider.Control>
    </Slider.Root>
  )
}
```

### NumberInput

```tsx
import type { FC } from 'react'
import { NumberInput } from '@chakra-ui/react'

interface NumberInputFieldProps {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
}

const NumberInputField: FC<NumberInputFieldProps> = ({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
}) => {
  return (
    <NumberInput.Root
      value={String(value)}
      onValueChange={(details) => onChange(details.valueAsNumber)}
      min={min}
      max={max}
      step={step}
    >
      <NumberInput.Field />
      <NumberInput.Control>
        <NumberInput.IncrementTrigger />
        <NumberInput.DecrementTrigger />
      </NumberInput.Control>
    </NumberInput.Root>
  )
}
```

### Select (Custom)

```tsx
import type { FC } from 'react'
import { Select, Portal } from '@chakra-ui/react'

interface SelectOption {
  value: string
  label: string
}

interface SelectFieldProps {
  options: SelectOption[]
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

const SelectField: FC<SelectFieldProps> = ({ options, value, onChange, placeholder }) => {
  return (
    <Select.Root
      value={[value]}
      onValueChange={(details) => onChange(details.value[0])}
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
  )
}
```

### PinInput

```tsx
import type { FC } from 'react'
import { PinInput, HStack } from '@chakra-ui/react'

interface OTPInputProps {
  length?: number
  onComplete: (value: string) => void
}

const OTPInput: FC<OTPInputProps> = ({ length = 4, onComplete }) => {
  return (
    <PinInput.Root onValueComplete={(details) => onComplete(details.value)}>
      <PinInput.HiddenInput />
      <PinInput.Control>
        <HStack>
          {Array.from({ length }).map((_, index) => (
            <PinInput.Input key={index} index={index} />
          ))}
        </HStack>
      </PinInput.Control>
    </PinInput.Root>
  )
}
```

### FileUpload

```tsx
import type { FC } from 'react'
import { FileUpload, Button } from '@chakra-ui/react'

interface FileUploadFieldProps {
  accept?: string
  multiple?: boolean
  onFilesChange: (files: File[]) => void
}

const FileUploadField: FC<FileUploadFieldProps> = ({
  accept = 'image/*',
  multiple = false,
  onFilesChange,
}) => {
  return (
    <FileUpload.Root
      accept={accept}
      multiple={multiple}
      onFilesChange={(details) => onFilesChange(details.acceptedFiles)}
    >
      <FileUpload.Trigger asChild>
        <Button variant="outline">Upload File</Button>
      </FileUpload.Trigger>
      <FileUpload.ItemGroup>
        <FileUpload.Context>
          {({ acceptedFiles }) =>
            acceptedFiles.map((file) => (
              <FileUpload.Item key={file.name} file={file}>
                <FileUpload.ItemPreview />
                <FileUpload.ItemName />
                <FileUpload.ItemSizeText />
                <FileUpload.ItemDeleteTrigger />
              </FileUpload.Item>
            ))
          }
        </FileUpload.Context>
      </FileUpload.ItemGroup>
      <FileUpload.HiddenInput />
    </FileUpload.Root>
  )
}
```

## Overlay

### Drawer

```tsx
import type { FC, ReactNode } from 'react'
import { Button, Drawer, Portal } from '@chakra-ui/react'

type DrawerPlacement = 'left' | 'right' | 'top' | 'bottom'

interface DrawerPanelProps {
  title: string
  trigger: ReactNode
  placement?: DrawerPlacement
  children: ReactNode
}

const DrawerPanel: FC<DrawerPanelProps> = ({
  title,
  trigger,
  placement = 'right',
  children,
}) => {
  return (
    <Drawer.Root placement={placement}>
      <Drawer.Trigger asChild>{trigger}</Drawer.Trigger>
      <Portal>
        <Drawer.Backdrop />
        <Drawer.Positioner>
          <Drawer.Content>
            <Drawer.Header>
              <Drawer.Title>{title}</Drawer.Title>
            </Drawer.Header>
            <Drawer.Body>{children}</Drawer.Body>
            <Drawer.Footer>
              <Drawer.CloseTrigger asChild>
                <Button variant="outline">Close</Button>
              </Drawer.CloseTrigger>
            </Drawer.Footer>
            <Drawer.CloseTrigger />
          </Drawer.Content>
        </Drawer.Positioner>
      </Portal>
    </Drawer.Root>
  )
}
```

### Popover

```tsx
import type { FC, ReactNode } from 'react'
import { Popover, Portal } from '@chakra-ui/react'

interface PopoverCardProps {
  trigger: ReactNode
  title?: string
  children: ReactNode
}

const PopoverCard: FC<PopoverCardProps> = ({ trigger, title, children }) => {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>{trigger}</Popover.Trigger>
      <Portal>
        <Popover.Positioner>
          <Popover.Content>
            <Popover.Arrow>
              <Popover.ArrowTip />
            </Popover.Arrow>
            {title && (
              <Popover.Header>
                <Popover.Title>{title}</Popover.Title>
              </Popover.Header>
            )}
            <Popover.Body>{children}</Popover.Body>
            <Popover.CloseTrigger />
          </Popover.Content>
        </Popover.Positioner>
      </Portal>
    </Popover.Root>
  )
}
```

### Tooltip

```tsx
import type { FC, ReactNode } from 'react'
import { Tooltip } from '@chakra-ui/react'

interface TooltipWrapperProps {
  label: string
  children: ReactNode
}

const TooltipWrapper: FC<TooltipWrapperProps> = ({ label, children }) => {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Positioner>
        <Tooltip.Content>
          <Tooltip.Arrow>
            <Tooltip.ArrowTip />
          </Tooltip.Arrow>
          {label}
        </Tooltip.Content>
      </Tooltip.Positioner>
    </Tooltip.Root>
  )
}
```

## Navigation

### Breadcrumb

```tsx
import type { FC } from 'react'
import { Breadcrumb } from '@chakra-ui/react'

interface BreadcrumbItem {
  label: string
  href?: string
}

interface BreadcrumbNavProps {
  items: BreadcrumbItem[]
}

const BreadcrumbNav: FC<BreadcrumbNavProps> = ({ items }) => {
  return (
    <Breadcrumb.Root>
      <Breadcrumb.List>
        {items.map((item, index) => (
          <Breadcrumb.Item key={item.label}>
            {index < items.length - 1 ? (
              <>
                <Breadcrumb.Link href={item.href}>{item.label}</Breadcrumb.Link>
                <Breadcrumb.Separator />
              </>
            ) : (
              <Breadcrumb.CurrentLink>{item.label}</Breadcrumb.CurrentLink>
            )}
          </Breadcrumb.Item>
        ))}
      </Breadcrumb.List>
    </Breadcrumb.Root>
  )
}
```

### Link

```tsx
import type { FC, ReactNode } from 'react'
import { Link, LinkOverlay, LinkBox, Text } from '@chakra-ui/react'

// Basic links
const BasicLinks: FC = () => (
  <>
    <Link href="/about">About Us</Link>
    <Link href="https://external.com" external>External Link</Link>
  </>
)

// Link card pattern
interface LinkCardProps {
  href: string
  title: string
  description: string
}

const LinkCard: FC<LinkCardProps> = ({ href, title, description }) => {
  return (
    <LinkBox as="article" p="4" borderWidth="1px" rounded="md">
      <Text fontWeight="bold">
        <LinkOverlay href={href}>{title}</LinkOverlay>
      </Text>
      <Text color="fg.muted">{description}</Text>
    </LinkBox>
  )
}
```

### Pagination

```tsx
import type { FC } from 'react'
import { Pagination } from '@chakra-ui/react'

interface PaginationControlProps {
  total: number
  pageSize: number
  currentPage: number
  onPageChange: (page: number) => void
}

const PaginationControl: FC<PaginationControlProps> = ({
  total,
  pageSize,
  currentPage,
  onPageChange,
}) => {
  return (
    <Pagination.Root
      count={total}
      pageSize={pageSize}
      page={currentPage}
      onPageChange={(details) => onPageChange(details.page)}
    >
      <Pagination.PrevTrigger />
      <Pagination.Items />
      <Pagination.NextTrigger />
    </Pagination.Root>
  )
}
```

### Steps

```tsx
import type { FC } from 'react'
import { Steps } from '@chakra-ui/react'

interface Step {
  title: string
  description?: string
}

interface StepperProps {
  steps: Step[]
  currentStep: number
}

const Stepper: FC<StepperProps> = ({ steps, currentStep }) => {
  return (
    <Steps.Root step={currentStep} count={steps.length}>
      <Steps.List>
        {steps.map((step, index) => (
          <Steps.Item key={index} index={index}>
            <Steps.Trigger>
              <Steps.Indicator />
              <Steps.Title>{step.title}</Steps.Title>
            </Steps.Trigger>
            <Steps.Separator />
          </Steps.Item>
        ))}
      </Steps.List>
    </Steps.Root>
  )
}
```

## Disclosure

### Accordion

```tsx
import type { FC } from 'react'
import { Accordion } from '@chakra-ui/react'

interface AccordionItem {
  value: string
  title: string
  content: React.ReactNode
}

interface AccordionListProps {
  items: AccordionItem[]
  allowMultiple?: boolean
  defaultValue?: string[]
}

const AccordionList: FC<AccordionListProps> = ({
  items,
  allowMultiple = false,
  defaultValue,
}) => {
  return (
    <Accordion.Root
      collapsible={!allowMultiple}
      multiple={allowMultiple}
      defaultValue={defaultValue}
    >
      {items.map((item) => (
        <Accordion.Item key={item.value} value={item.value}>
          <Accordion.ItemTrigger>
            <Accordion.ItemIndicator />
            {item.title}
          </Accordion.ItemTrigger>
          <Accordion.ItemContent>{item.content}</Accordion.ItemContent>
        </Accordion.Item>
      ))}
    </Accordion.Root>
  )
}
```

### Collapsible

```tsx
import type { FC, ReactNode } from 'react'
import { Collapsible, Button } from '@chakra-ui/react'

interface CollapsibleSectionProps {
  triggerLabel: string
  children: ReactNode
  defaultOpen?: boolean
}

const CollapsibleSection: FC<CollapsibleSectionProps> = ({
  triggerLabel,
  children,
  defaultOpen = false,
}) => {
  return (
    <Collapsible.Root defaultOpen={defaultOpen}>
      <Collapsible.Trigger asChild>
        <Button variant="outline">{triggerLabel}</Button>
      </Collapsible.Trigger>
      <Collapsible.Content>{children}</Collapsible.Content>
    </Collapsible.Root>
  )
}
```

## Typography

```tsx
import type { FC } from 'react'
import { Heading, Text, Em, Strong, Code, Kbd, Stack } from '@chakra-ui/react'

const TypographyExamples: FC = () => {
  return (
    <Stack gap="4">
      {/* Headings */}
      <Heading as="h1" size="2xl">Main Title</Heading>
      <Heading as="h2" size="xl">Section Title</Heading>
      <Heading as="h3" size="lg">Subsection</Heading>

      {/* Text variants */}
      <Text fontSize="lg">Large text</Text>
      <Text fontSize="md">Normal text</Text>
      <Text fontSize="sm" color="fg.muted">Small muted text</Text>

      {/* Inline styles */}
      <Text>
        This is <Em>emphasized</Em> and <Strong>important</Strong> text.
      </Text>

      {/* Code and keyboard */}
      <Text>
        Run <Code>npm install</Code> to install dependencies.
      </Text>
      <Text>
        Press <Kbd>Ctrl</Kbd> + <Kbd>C</Kbd> to copy.
      </Text>
    </Stack>
  )
}
```

## Media

### Image

```tsx
import type { FC } from 'react'
import { Image } from '@chakra-ui/react'

interface ResponsiveImageProps {
  src: string
  alt: string
  fallbackSrc?: string
}

const ResponsiveImage: FC<ResponsiveImageProps> = ({ src, alt, fallbackSrc }) => {
  return (
    <Image
      src={src}
      alt={alt}
      borderRadius="lg"
      objectFit="cover"
      fallbackSrc={fallbackSrc ?? '/placeholder.jpg'}
    />
  )
}
```

### AspectRatio

```tsx
import type { FC } from 'react'
import { AspectRatio, Image } from '@chakra-ui/react'

interface VideoThumbnailProps {
  src: string
  alt: string
  ratio?: number
}

const VideoThumbnail: FC<VideoThumbnailProps> = ({ src, alt, ratio = 16 / 9 }) => {
  return (
    <AspectRatio ratio={ratio}>
      <Image src={src} alt={alt} objectFit="cover" />
    </AspectRatio>
  )
}

interface EmbedProps {
  src: string
  title: string
}

const VideoEmbed: FC<EmbedProps> = ({ src, title }) => {
  return (
    <AspectRatio ratio={16 / 9}>
      <iframe src={src} title={title} allowFullScreen />
    </AspectRatio>
  )
}
```

## Empty State

```tsx
import type { FC, ReactNode } from 'react'
import { EmptyState, Button } from '@chakra-ui/react'

interface EmptyStateViewProps {
  icon: ReactNode
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
}

const EmptyStateView: FC<EmptyStateViewProps> = ({ icon, title, description, action }) => {
  return (
    <EmptyState.Root>
      <EmptyState.Content>
        <EmptyState.Indicator>{icon}</EmptyState.Indicator>
        <EmptyState.Title>{title}</EmptyState.Title>
        <EmptyState.Description>{description}</EmptyState.Description>
        {action && (
          <Button onClick={action.onClick}>{action.label}</Button>
        )}
      </EmptyState.Content>
    </EmptyState.Root>
  )
}
```
