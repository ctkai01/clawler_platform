import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/components/PageHeader'
import { cn } from '@/lib/utils'

export function EntityKeywordPicker() {
  const queryClient = useQueryClient()
  const [entitySearch, setEntitySearch] = useState('')

  const { data: entities, isLoading: loadingEntities } = useQuery({
    queryKey: ['org', 'entities'],
    queryFn: orgApi.listEntities,
  })
  const { data: keywords, isLoading: loadingKeywords } = useQuery({
    queryKey: ['org', 'keywords'],
    queryFn: orgApi.listKeywords,
  })

  const toggleEntity = useMutation({
    mutationFn: ({ name, selected }: { name: string; selected: boolean }) =>
      selected ? orgApi.deselectEntity(name) : orgApi.selectEntity(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org', 'entities'] }),
  })

  const toggleKeyword = useMutation({
    mutationFn: ({ id, selected }: { id: number; selected: boolean }) =>
      selected ? orgApi.deselectKeyword(id) : orgApi.selectKeyword(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org', 'keywords'] }),
  })

  const selectedEntities = useMemo(() => entities?.filter((e) => e.is_selected) ?? [], [entities])
  const searchResults = useMemo(() => {
    const q = entitySearch.trim().toLowerCase()
    if (!q || !entities) return []
    return entities.filter((e) => e.canonical_name.toLowerCase().includes(q)).slice(0, 40)
  }, [entities, entitySearch])

  const EntityPill = ({ name, selected }: { name: string; selected: boolean }) => (
    <button
      type="button"
      onClick={() => toggleEntity.mutate({ name, selected })}
      className={cn(
        'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
        selected
          ? 'border-accent-ink bg-accent-ink text-white'
          : 'border-line bg-surface text-muted hover:border-accent-ink hover:text-accent-ink',
      )}
    >
      {name}
    </button>
  )

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Entity / Keyword theo dõi"
        description={`Chọn từ ${entities?.length.toLocaleString('vi-VN') ?? '…'} entity trong entity_gazetteer.`}
      />

      <Card>
        <div className="text-xs font-semibold uppercase tracking-wide text-muted">Entity đang theo dõi</div>
        {loadingEntities ? (
          <p className="mt-2 text-sm text-muted">Đang tải…</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {selectedEntities.length > 0 ? (
              selectedEntities.map((e) => <EntityPill key={e.canonical_name} name={e.canonical_name} selected />)
            ) : (
              <p className="text-sm text-muted">Chưa chọn entity nào — tìm bên dưới để thêm.</p>
            )}
          </div>
        )}

        <Input
          className="mt-4"
          placeholder="Tìm entity (VD: MobiFone, Viettel…)"
          value={entitySearch}
          onChange={(e) => setEntitySearch(e.target.value)}
        />
        {searchResults.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
            {searchResults.map((e) => (
              <EntityPill key={e.canonical_name} name={e.canonical_name} selected={e.is_selected} />
            ))}
          </div>
        )}
      </Card>

      <Card className="mt-4">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted">Keyword</div>
        {loadingKeywords ? (
          <p className="mt-2 text-sm text-muted">Đang tải…</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {keywords?.map((k) => (
              <button
                key={k.keyword_id}
                type="button"
                onClick={() => toggleKeyword.mutate({ id: k.keyword_id, selected: k.is_selected })}
                className={cn(
                  'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
                  k.is_selected
                    ? 'border-accent-ink bg-accent-ink text-white'
                    : 'border-line bg-surface text-muted hover:border-accent-ink hover:text-accent-ink',
                )}
              >
                {k.term}
                <span className="ml-1.5 text-[10px] opacity-70">{k.category}</span>
              </button>
            ))}
            {keywords?.length === 0 && <p className="text-sm text-muted">Chưa có keyword nào trong danh mục.</p>}
          </div>
        )}
      </Card>
    </div>
  )
}
