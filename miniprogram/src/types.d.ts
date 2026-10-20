/// <reference types="@tarojs/taro" />

declare module '*.scss'

declare namespace NodeJS {
  interface ProcessEnv {
    TARO_ENV: 'weapp' | 'h5'
    TARO_APP_API_BASE: string
  }
}