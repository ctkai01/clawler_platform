export function AuthSplitPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-svh">
      <div className="relative hidden w-[42%] flex-col justify-between overflow-hidden bg-ink px-12 py-14 text-white lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, white 1px, transparent 0)',
            backgroundSize: '28px 28px',
          }}
        />
        <div className="relative">
          <div className="font-display flex items-baseline gap-1.5 text-lg font-semibold tracking-tight">
            <span className="text-accent">◈</span> Monitoring Post
          </div>
          <div className="mt-0.5 text-xs uppercase tracking-wider text-white/40">Reputation Management Platform</div>
        </div>

        <div className="relative max-w-sm">
          <p className="font-display text-[1.7rem] font-medium leading-snug text-white text-balance">
            Mọi nhắc đến thương hiệu bạn, từ Facebook đến báo chí, gom về một nơi.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-white/55">
            Chọn thực thể và từ khóa cần theo dõi, phân quyền đúng người đúng nguồn — số liệu cập nhật theo thời gian
            thực.
          </p>
        </div>

        <div className="relative text-xs text-white/30">© {new Date().getFullYear()} Reputation Management Platform</div>
      </div>

      <div className="flex flex-1 items-center justify-center bg-paper px-6 py-12">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  )
}
