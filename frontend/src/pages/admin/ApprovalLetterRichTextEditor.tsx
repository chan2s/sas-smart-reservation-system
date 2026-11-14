import { Extension, Node as TiptapNode, type JSONContent } from '@tiptap/core'
import { EditorContent, NodeViewWrapper, ReactNodeViewRenderer, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import TextAlign from '@tiptap/extension-text-align'
import { Plugin } from '@tiptap/pm/state'
import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  ArrowDown,
  ArrowUp,
  Bold,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  List,
  ListOrdered,
  Plus,
  Trash2,
} from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Form'
import type { ApprovalLetterDocument } from '@/lib/types'

const LOCKED_BLOCKS = new Set(['documentMetadata', 'reservationDetails', 'reservationConditions'])

const ParagraphSpacing = Extension.create({
  name: 'paragraphSpacing',
  addGlobalAttributes() {
    return [{
      types: ['paragraph', 'heading'],
      attributes: {
        spaceAfter: {
          default: 4,
          parseHTML: (element: HTMLElement) => Number(element.getAttribute('data-space-after') ?? 4),
          renderHTML: (attributes: { spaceAfter?: number }) => ({
            'data-space-after': attributes.spaceAfter ?? 4,
          }),
        },
      },
    }]
  },
})

function ProtectedBlock({ node }: { node: { type: { name: string } } }) {
  const labels: Record<string, [string, string]> = {
    documentMetadata: ['Reference and issue date', 'Filled from the selected reservation and today’s date.'],
    reservationDetails: ['Reservation details table', 'Filled from the selected reservation. Its layout stays application-managed.'],
    reservationConditions: ['Reservation conditions', 'Current facility rules and reservation requirements are inserted here.'],
  }
  const [title, description] = labels[node.type.name]
  return (
    <NodeViewWrapper
      as="div"
      contentEditable={false}
      className="my-3 rounded-lg border border-dashed border-brand/40 bg-brand-soft/60 px-4 py-3"
      data-testid={`protected-${node.type.name}`}
    >
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-0.5 text-xs text-muted">{description}</p>
    </NodeViewWrapper>
  )
}

function protectedNode(name: string) {
  return TiptapNode.create({
    name,
    group: 'block',
    atom: true,
    selectable: false,
    draggable: false,
    parseHTML: () => [{ tag: `div[data-letter-block="${name}"]` }],
    renderHTML: ({ HTMLAttributes }) => ['div', { ...HTMLAttributes, 'data-letter-block': name }, name],
    addNodeView: () => ReactNodeViewRenderer(ProtectedBlock),
  })
}

const ProtectedBlocks = Extension.create({
  name: 'protectLetterBlocks',
  addProseMirrorPlugins() {
    return [new Plugin({
      filterTransaction: (transaction, state) => {
        if (!transaction.docChanged) return true
        const blockOrder = (doc: typeof state.doc) => {
          const order: string[] = []
          doc.descendants((node) => {
            if (LOCKED_BLOCKS.has(node.type.name)) order.push(node.type.name)
          })
          return order
        }
        const before = blockOrder(state.doc)
        const after = blockOrder(transaction.doc)
        return before.length === after.length && before.every((name, index) => name === after[index])
      },
    })]
  },
})

const extensions = [
  StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
  TextAlign.configure({ types: ['paragraph', 'heading'], alignments: ['left', 'center', 'right', 'justify'] }),
  ParagraphSpacing,
  protectedNode('documentMetadata'),
  protectedNode('reservationDetails'),
  protectedNode('reservationConditions'),
  ProtectedBlocks,
]

type Props = {
  value: ApprovalLetterDocument
  disabled: boolean
  onChange: (value: ApprovalLetterDocument) => void
  placeholders: Array<[string, string]>
}

function activeBlockIndex(editor: NonNullable<ReturnType<typeof useEditor>>) {
  const position = editor.state.selection.from
  let selected = 0
  editor.state.doc.forEach((node, offset, index) => {
    if (position >= offset && position <= offset + node.nodeSize) selected = index
  })
  return selected
}

export function ApprovalLetterRichTextEditor({ value, disabled, onChange, placeholders }: Props) {
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const editor = useEditor({
    extensions,
    content: value as JSONContent,
    editable: !disabled,
    immediatelyRender: false,
    onUpdate: ({ editor: updated }) => onChangeRef.current(updated.getJSON() as ApprovalLetterDocument),
  })

  const serializedValue = JSON.stringify(value)
  useEffect(() => {
    if (!editor || JSON.stringify(editor.getJSON()) === serializedValue) return
    editor.commands.setContent(value as JSONContent, { emitUpdate: false })
  }, [editor, serializedValue, value])

  useEffect(() => {
    editor?.setEditable(!disabled)
  }, [disabled, editor])

  if (!editor) return <div className="min-h-64 rounded-lg border border-line bg-white" role="status">Loading document editor…</div>

  const selectedIndex = activeBlockIndex(editor)
  const topBlocks = editor.getJSON().content ?? []
  const selectedBlock = topBlocks[selectedIndex]
  const nextBlock = topBlocks[selectedIndex + 1]
  const isLocked = !selectedBlock || LOCKED_BLOCKS.has(selectedBlock.type ?? '')
  const spacing = String(selectedBlock?.attrs?.spaceAfter ?? 4)

  function moveCurrentBlock(direction: -1 | 1) {
    const content = [...(editor?.getJSON().content ?? [])]
    const index = activeBlockIndex(editor!)
    const target = index + direction
    if (
      index < 0 || target < 0 || target >= content.length ||
      LOCKED_BLOCKS.has(content[index]?.type ?? '') ||
      LOCKED_BLOCKS.has(content[target]?.type ?? '')
    ) return
    ;[content[index], content[target]] = [content[target], content[index]]
    const next = { type: 'doc', content } as ApprovalLetterDocument
    editor!.commands.setContent(next as JSONContent)
    onChangeRef.current(next)
  }

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-white">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line bg-soft/70 p-2" aria-label="Letter formatting toolbar">
        <Button type="button" size="sm" variant={editor.isActive('bold') ? 'secondary' : 'outline'} disabled={disabled} aria-label="Bold" aria-pressed={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()} icon={<Bold className="size-4" />} />
        <Button type="button" size="sm" variant={editor.isActive('italic') ? 'secondary' : 'outline'} disabled={disabled} aria-label="Italic" aria-pressed={editor.isActive('italic')} onClick={() => editor.chain().focus().toggleItalic().run()} icon={<Italic className="size-4" />} />
        <span className="mx-1 h-6 w-px bg-line" aria-hidden />
        <Button type="button" size="sm" variant={editor.isActive('heading', { level: 2 }) ? 'secondary' : 'outline'} disabled={disabled} aria-label="Heading 2" onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} icon={<Heading2 className="size-4" />} />
        <Button type="button" size="sm" variant={editor.isActive('heading', { level: 1 }) ? 'secondary' : 'outline'} disabled={disabled} aria-label="Heading 1" onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} icon={<Heading1 className="size-4" />} />
        <Button type="button" size="sm" variant={editor.isActive('heading', { level: 3 }) ? 'secondary' : 'outline'} disabled={disabled} aria-label="Heading 3" onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} icon={<Heading3 className="size-4" />} />
        <Button type="button" size="sm" variant="outline" disabled={disabled} aria-label="Bulleted list" onClick={() => editor.chain().focus().toggleBulletList().run()} icon={<List className="size-4" />} />
        <Button type="button" size="sm" variant="outline" disabled={disabled} aria-label="Numbered list" onClick={() => editor.chain().focus().toggleOrderedList().run()} icon={<ListOrdered className="size-4" />} />
        <span className="mx-1 h-6 w-px bg-line" aria-hidden />
        <Button type="button" size="sm" variant="outline" disabled={disabled} aria-label="Align left" onClick={() => editor.chain().focus().setTextAlign('left').run()} icon={<AlignLeft className="size-4" />} />
        <Button type="button" size="sm" variant="outline" disabled={disabled} aria-label="Align center" onClick={() => editor.chain().focus().setTextAlign('center').run()} icon={<AlignCenter className="size-4" />} />
        <Button type="button" size="sm" variant="outline" disabled={disabled} aria-label="Align right" onClick={() => editor.chain().focus().setTextAlign('right').run()} icon={<AlignRight className="size-4" />} />
        <Button type="button" size="sm" variant="outline" disabled={disabled} aria-label="Justify" onClick={() => editor.chain().focus().setTextAlign('justify').run()} icon={<AlignJustify className="size-4" />} />
        <label className="ml-auto flex items-center gap-2 text-xs text-muted">
          Paragraph spacing
          <Select
            aria-label="Paragraph spacing"
            className="h-8 w-24 bg-white"
            value={spacing}
            disabled={disabled || isLocked}
            onChange={(event) => {
              const type = editor.isActive('heading') ? 'heading' : 'paragraph'
              editor.chain().focus().updateAttributes(type, { spaceAfter: Number(event.target.value) }).run()
            }}
          >
            {[0, 2, 4, 8, 12, 16, 24].map((value) => <option key={value} value={value}>{value} pt</option>)}
          </Select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => editor.chain().focus().insertContentAt(editor.state.doc.content.size - 1, { type: 'paragraph' }).run()} icon={<Plus className="size-4" />}>Add paragraph</Button>
        <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => editor.chain().focus().insertContentAt(editor.state.doc.content.size - 1, { type: 'heading', attrs: { level: 2, textAlign: 'left', spaceAfter: 4 }, content: [{ type: 'text', text: 'New section' }] }).run()} icon={<Plus className="size-4" />}>Add heading</Button>
        <Button type="button" size="sm" variant="outline" disabled={disabled || isLocked} aria-label="Move block up" onClick={() => moveCurrentBlock(-1)} icon={<ArrowUp className="size-4" />} />
        <Button type="button" size="sm" variant="outline" disabled={disabled || isLocked || !nextBlock || LOCKED_BLOCKS.has(nextBlock.type ?? '')} aria-label="Move block down" onClick={() => moveCurrentBlock(1)} icon={<ArrowDown className="size-4" />} />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={disabled || isLocked || topBlocks.length <= 3}
          aria-label="Remove current block"
          onClick={() => {
            const index = activeBlockIndex(editor)
            if (index < 0 || LOCKED_BLOCKS.has(topBlocks[index]?.type ?? '')) return
            let from = 0
            for (let childIndex = 0; childIndex < index; childIndex += 1) {
              from += editor.state.doc.child(childIndex).nodeSize
            }
            const block = editor.state.doc.child(index)
            editor.chain().focus().deleteRange({ from, to: from + block.nodeSize }).run()
          }}
          icon={<Trash2 className="size-4" />}
        >Remove block</Button>
        <span className="text-xs text-muted">Select a paragraph or heading to move or remove it. Protected data blocks cannot be removed.</span>
      </div>

      <EditorContent
        editor={editor}
        className="approval-letter-editor max-h-[680px] min-h-[460px] overflow-y-auto px-5 py-4 sm:px-8 sm:py-6"
      />

      <div className="border-t border-line bg-soft/50 p-4">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-brand">Insert a supported placeholder</summary>
          <p className="mt-1 text-xs text-muted">The editor shows these as template variables. Reservation details appear only in a selected reservation’s preview or generated letter.</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {placeholders.map(([token, description]) => (
              <div key={token} className="flex min-w-0 items-start justify-between gap-2 rounded-lg border border-line bg-white p-2">
                <div className="min-w-0">
                  <code className="text-xs font-semibold text-ink">{token}</code>
                  <p className="text-xs text-muted">{description}</p>
                </div>
                <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => editor.chain().focus().insertContent(token).run()}>Insert</Button>
              </div>
            ))}
          </div>
        </details>
      </div>
    </div>
  )
}
