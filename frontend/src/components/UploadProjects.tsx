import { useEffect, useRef, useState } from 'react'
import type { Project } from '../types'
import { CSV_TEMPLATE, reviewCsv, type ImportBatch } from '../importProjects'
import Icon from './Icon'

export default function UploadProjects({ existing, onClose, onImport }: {
  existing: Project[]; onClose: () => void; onImport: (batch: ImportBatch) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const [batch, setBatch] = useState<ImportBatch | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  useEffect(() => { dialog.current?.showModal() }, [])
  async function read(file?: File) {
    if (!file) return
    setError(''); setBatch(null)
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('Choose a CSV spreadsheet. PDF and Excel files are not supported yet.'); return }
    if (file.size > 2_000_000) { setError('Choose a CSV smaller than 2 MB.'); return }
    setBusy(true)
    try {
      const id = crypto.randomUUID()
      setBatch({ id, filename: file.name, rows: reviewCsv(await file.text(), id, existing) })
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not read this file.') }
    finally { setBusy(false) }
  }
  const ready = batch?.rows.filter(r => r.project).length ?? 0
  const flagged = (batch?.rows.length ?? 0) - ready
  return (
    <dialog ref={dialog} className="upload-dialog" aria-labelledby="upload-title" onCancel={onClose} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="upload-shell">
        <header className="upload-heading">
          <div className="upload-symbol"><Icon name="upload" size={23} /></div>
          <button className="icon-button" onClick={onClose} aria-label="Close upload"><Icon name="close" /></button>
        </header>
        <p className="eyebrow">ADD TO WORKSPACE</p>
        <h2 id="upload-title">Bring your plans to the map.</h2>
        <p className="upload-intro">Upload proposed projects. Find nearby work, compare timelines, and see where coordination could make sense.</p>
        <div className="upload-steps"><span className={!batch ? 'current' : ''}>01 / Upload</span><span className={batch ? 'current' : ''}>02 / Review</span><span>03 / Compare</span></div>
        {!batch ? <>
          <button className={`drop-zone ${dragging ? 'dragging' : ''}`} onClick={() => input.current?.click()} disabled={busy}
            onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)}
            onDrop={e => { e.preventDefault(); setDragging(false); void read(e.dataTransfer.files[0]) }}>
            <Icon name="file" size={32} />
            <strong>{busy ? 'Reading projects…' : 'Drop your project spreadsheet here'}</strong>
            <span>or <u>choose a file</u></span>
            <small>CSV · up to 2 MB · 1,000 projects</small>
          </button>
          <input ref={input} type="file" accept=".csv,text/csv" aria-label="Project CSV" className="sr-only" onChange={e => void read(e.target.files?.[0])} />
          <div className="template-row"><div><strong>Start with the right columns</strong><p>Utility, project name, coordinates, in-service date.</p></div>
            <a className="text-link" href={`data:text/csv;charset=utf-8,${encodeURIComponent(CSV_TEMPLATE)}`} download="gridwatch-project-template.csv"><Icon name="download" size={16} /> Template</a>
          </div>
        </> : <div className="import-review">
          <div className="review-file"><Icon name="file" /><strong>{batch.filename}</strong><button className="text-link" onClick={() => setBatch(null)}>Change file</button></div>
          <div className="review-counts"><div><strong>{ready}</strong><span>Ready to map</span></div><div><strong>{flagged}</strong><span>Need attention</span></div></div>
          <div className="review-rows">{batch.rows.map(row => <div className="review-row" key={row.row}>
            <span className={row.project ? 'status-dot ready' : 'status-dot flagged'} />
            <div><strong>{row.name}</strong><p>{row.issues.length ? row.issues.join(' · ') : `${row.project!.utility} · ${row.project!.in_service_date}`}</p></div><small>Row {row.row}</small>
          </div>)}</div>
          {flagged > 0 && <p className="review-note">Flagged rows won’t be mapped. Correct them in your spreadsheet and upload again.</p>}
          <p className="review-note">Uploaded coordinates are marked unverified. Nearby projects are candidates for review, not confirmed shared construction.</p>
        </div>}
        {error && <p role="alert" className="upload-error">{error}</p>}
        <footer className="upload-footer"><span><Icon name="layers" size={15} /> Local to this tab. Refresh clears uploads.</span>
          {batch && <button className="primary-button" disabled={!ready} onClick={() => { onImport(batch); onClose() }}>Add {ready} project{ready !== 1 ? 's' : ''} & compare <Icon name="arrow" size={16} /></button>}
        </footer>
      </div>
    </dialog>
  )
}
