import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import zh from './zh.json'
import en from './en.json'

const STORAGE_KEY = 'lang'
const savedLang = (typeof window !== 'undefined' && localStorage.getItem(STORAGE_KEY)) || 'zh'

// 同步 <html lang>，讓 a11y / SEO / 瀏覽器斷詞依當前語言（zh → zh-Hant）。
function syncDocLang(lang: string) {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang === 'zh' ? 'zh-Hant' : 'en'
  }
}

i18n.use(initReactI18next).init({
  resources: {
    zh: { translation: zh },
    en: { translation: en },
  },
  lng: savedLang,
  fallbackLng: 'zh',
  interpolation: { escapeValue: false },
})
syncDocLang(savedLang)

export function toggleLang() {
  const next = i18n.language === 'zh' ? 'en' : 'zh'
  i18n.changeLanguage(next)
  localStorage.setItem(STORAGE_KEY, next)
  syncDocLang(next)
}

export default i18n
