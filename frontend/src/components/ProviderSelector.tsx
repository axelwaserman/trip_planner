import { Box, Flex, Text } from '@chakra-ui/react'
import type { ChangeEvent } from 'react'
import { useEffect, useState } from 'react'
import { apiFetch } from '../lib/auth'
import { PROVIDERS_FETCH_FAILED, type ProviderErrorView } from '../lib/providerErrors'

interface Provider {
  available: boolean
  models: string[]
}

interface Providers {
  [key: string]: Provider
}

interface ProviderSelectorProps {
  onProviderChange: (provider: string, model: string) => void
  onProviderError?: (error: ProviderErrorView) => void
  initialProvider?: string
  initialModel?: string
}

export function ProviderSelector({
  onProviderChange,
  onProviderError,
  initialProvider = 'ollama',
  initialModel = 'qwen3:4b',
}: ProviderSelectorProps) {
  const [providers, setProviders] = useState<Providers>({})
  const [selectedProvider, setSelectedProvider] = useState(initialProvider)
  const [selectedModel, setSelectedModel] = useState(initialModel)
  const [loading, setLoading] = useState(true)

  // Fetch available providers on mount
  useEffect(() => {
    const fetchProviders = async () => {
      try {
        const response = await apiFetch('/api/providers')
        if (!response.ok) {
          throw new Error('Failed to fetch providers')
        }
        const data = await response.json()
        setProviders(data)

        // Load from localStorage if available
        const saved = localStorage.getItem('llm_provider_config')
        if (saved) {
          const { provider, model } = JSON.parse(saved)
          if (data[provider]?.available) {
            setSelectedProvider(provider)
            setSelectedModel(model)
          }
        }
      } catch {
        // apiFetch handles 401 via redirect; surface every other failure as F4.
        onProviderError?.(PROVIDERS_FETCH_FAILED)
      } finally {
        setLoading(false)
      }
    }

    fetchProviders()
  }, [onProviderError])

  // Save to localStorage and notify parent when selection changes
  const handleProviderChange = (newProvider: string) => {
    setSelectedProvider(newProvider)
    
    // Set first available model for the new provider
    const firstModel = providers[newProvider]?.models[0] || ''
    setSelectedModel(firstModel)
    
    // Save to localStorage
    localStorage.setItem(
      'llm_provider_config',
      JSON.stringify({ provider: newProvider, model: firstModel })
    )
    
    // Notify parent
    onProviderChange(newProvider, firstModel)
  }

  const handleModelChange = (newModel: string) => {
    setSelectedModel(newModel)
    
    // Save to localStorage
    localStorage.setItem(
      'llm_provider_config',
      JSON.stringify({ provider: selectedProvider, model: newModel })
    )
    
    // Notify parent
    onProviderChange(selectedProvider, newModel)
  }

  if (loading) {
    return (
      <Text fontSize="sm" color="gray.500">
        Loading providers...
      </Text>
    )
  }

  // Show every provider the backend exposes — even those without credentials.
  // The probe runs at session-create and emits a structured F3 banner if the
  // user picks a provider whose API key is missing, so we let the user reach
  // that error path instead of hiding the option entirely.
  const allProviders = Object.entries(providers)

  if (allProviders.length === 0) {
    return (
      <Text fontSize="sm" color="red.500">
        No providers available
      </Text>
    )
  }

  return (
    <Flex gap={2} align="center">
      <Box>
        <select
          style={{
            padding: '0.25rem 0.5rem',
            borderRadius: '0.375rem',
            border: '1px solid #E2E8F0',
            fontSize: '0.875rem',
          }}
          value={selectedProvider}
          onChange={(e: ChangeEvent<HTMLSelectElement>) => handleProviderChange(e.target.value)}
          disabled={allProviders.length === 1}
        >
          {allProviders.map(([name]) => (
            <option key={name} value={name}>
              {name.charAt(0).toUpperCase() + name.slice(1)}
            </option>
          ))}
        </select>
      </Box>
      
      <Box>
        <select
          style={{
            padding: '0.25rem 0.5rem',
            borderRadius: '0.375rem',
            border: '1px solid #E2E8F0',
            fontSize: '0.875rem',
          }}
          value={selectedModel}
          onChange={(e: ChangeEvent<HTMLSelectElement>) => handleModelChange(e.target.value)}
        >
          {providers[selectedProvider]?.models.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </select>
      </Box>
    </Flex>
  )
}
