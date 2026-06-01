import { Component, ReactNode } from 'react'
import { withTranslation, WithTranslation } from 'react-i18next'

/**
 * React 錯誤邊界：捕住 children 在 render / lifecycle 拋出的錯誤，
 * 顯示降級 UI 並提供「重試」按鈕，避免單一元件壞掉就讓整頁白屏。
 *
 * 常見觸發點：
 * - lightweight-charts setData 收到不認識的 time 格式（ISO 字串、NaN…）
 * - API 回傳 schema 對不上前端假設
 *
 * 注意：error boundary 抓不到 async / setTimeout / event handler 內的錯誤，
 * 那些要靠 try-catch + setState 把錯誤搬回 render path。
 */
type Props = { children: ReactNode; label?: string; onReset?: () => void } & WithTranslation
type State = { error: Error | null }

class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    // 留個 console 線索方便除錯；正式環境可改接到上報服務
    console.error(`[ErrorBoundary${this.props.label ? ` · ${this.props.label}` : ''}]`, error, info.componentStack)
  }

  reset = () => {
    this.setState({ error: null })
    this.props.onReset?.()
  }

  render() {
    const { error } = this.state
    const { t } = this.props
    if (!error) return this.props.children
    return (
      <div className="bg-red-950/40 border border-red-800/50 rounded-lg p-4 text-sm">
        <p className="text-red-300 font-medium mb-1">
          {this.props.label ? `${this.props.label} ` : ''}{t('common.error_prefix')}
        </p>
        <p className="text-red-400/80 font-mono text-xs mb-3 break-all">{error.message}</p>
        <button onClick={this.reset}
          className="text-xs px-3 py-1 rounded bg-red-700/40 hover:bg-red-700/60 text-red-100">
          {t('common.retry')}
        </button>
      </div>
    )
  }
}

export default withTranslation()(ErrorBoundary)
