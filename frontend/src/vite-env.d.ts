/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Base URL of the backend API: http://localhost:8000 in local dev (see .env.example); the
   * relative `/api` in the deployed build (.do/app.yaml), so every hostname calls itself.
   */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
