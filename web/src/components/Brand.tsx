/** The 红笔君 mark: vermilion square seal plus the name set in the serif face. `size` is the seal's px size. */
export default function Brand({ size = 32 }: { size?: number }) {
  return (
    <span className="brand-mark">
      <img src={size > 32 ? '/brand/seal-128.png' : '/brand/seal-64.png'} width={size} height={size} alt="" />
      <span className="serif">红笔君</span>
    </span>
  )
}
