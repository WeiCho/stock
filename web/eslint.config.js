import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // 動態 API 資料目前以 `any` 標註；之後若要為各回應寫真實型別，再把這條打開
      '@typescript-eslint/no-explicit-any': 'off',
      // 對「在 effect 裡 setState」過嚴；資料抓取 + loading 狀態本來就需要這樣寫
      'react-hooks/set-state-in-effect': 'off',
    },
  },
])
