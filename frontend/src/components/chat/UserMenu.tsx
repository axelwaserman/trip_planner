import { Flex, IconButton, Text } from '@chakra-ui/react'
import { LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { clearToken } from '../../lib/auth'

interface UserMenuProps {
  username: string
}

export function UserMenu({ username }: UserMenuProps) {
  const navigate = useNavigate()

  function handleLogout() {
    clearToken()
    navigate('/login', { replace: true })
  }

  return (
    <Flex direction="row" gap="3" align="center">
      <Text fontSize="13px" color="fg.secondary">
        {username}
      </Text>
      <IconButton
        aria-label="Sign out"
        onClick={handleLogout}
        variant="ghost"
        size="sm"
        borderRadius="full"
      >
        <LogOut size={16} />
      </IconButton>
    </Flex>
  )
}
