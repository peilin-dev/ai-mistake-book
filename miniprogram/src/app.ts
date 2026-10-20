import { PropsWithChildren } from 'react'
import Taro, { useLaunch } from '@tarojs/taro'
import { login } from './lib/auth'
import './app.scss'

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    if (!Taro.getStorageSync('token')) {
      login().catch(() => {
        // Silent: request() logs in again on the first 401.
      })
    }
  })
  return children
}

export default App