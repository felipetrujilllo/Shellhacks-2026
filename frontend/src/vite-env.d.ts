/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the GridWatch backend, e.g. http://localhost:8000 (see .env.example). */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
