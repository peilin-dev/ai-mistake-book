import { useState } from 'react'
import { Link } from 'react-router-dom'
import Brand from '../components/Brand'
import Icon, { type IconName } from '../components/Icon'
import './landing.css'

const features: { icon: IconName; title: string; text: string; tag: string }[] = [
  { icon: 'upload', title: '一摞作业，一次上传', text: '支持批量上传试卷图片，将纸上的答案带进同一个工作流程。', tag: '批量上传' },
  { icon: 'pen', title: '看得见依据的批改', text: '原卷、得分、评分依据并排查看。AI 辅助批改，最终判断交给老师。', tag: '原卷对照' },
  { icon: 'chart', title: '从分数，看到问题', text: '按题查看作答情况与常见错因，让下一节讲评课更有针对性。', tag: '学情分析' },
  { icon: 'book', title: '让错题成为下一次进步', text: '串联错题整理、练习生成和打印，把一次批改延伸为一次巩固。', tag: '巩固练习' },
]
const faqs = [
  ['AI 批改后，老师还能修改吗？', '可以。老师可以对照原卷复核批改结果、调整总分。AI 原始评分明细仍会保留，帮助你了解评分依据。'],
  ['可以直接上传纸质作业吗？', '先将纸质作业拍照或扫描为图片，再批量上传。建议拍摄清晰、完整的试卷；上传后可查看每页的处理状态。'],
  ['首页展示的成绩是真实学生数据吗？', '不是。此页所有试卷、成绩、错因和练习均为合成示例，仅用于介绍产品流程，不包含真实学生信息。'],
  ['在哪里查看价格和批改额度？', '当前账号的月度额度可在登录后的账号区查看。本页付费方案为规划预览，价格与权益尚未发布，暂不支持在线购买。'],
]

function ProductDemo() {
  const [mode, setMode] = useState(0)
  return <div className="lp-demo" id="demo">
    <div className="lp-demo-bar"><span className="tw-flex tw-items-center tw-gap-2"><span className="lp-live-dot" /> 红笔君工作台</span><span className="lp-demo-label">交互演示 · 示例数据</span></div>
    <div className="lp-demo-body">
      <div className="lp-demo-sidebar"><span className="lp-mini-title">一份作业的旅程</span>{(['原卷批改', '学情分析', '巩固练习'] as const).map((label, index) => <button key={label} type="button" aria-pressed={mode === index} onClick={() => setMode(index)}><Icon name={(['pen', 'chart', 'book'] as const)[index]} /><span>{label}</span><span className="lp-step">0{index + 1}</span></button>)}<div className="lp-demo-note"><Icon name="clipboard" /><p>AI 帮你整理，<br />判断始终在你手中。</p></div></div>
      <div className="lp-demo-content" aria-live="polite">
        <div className="lp-demo-heading"><div><span className="lp-mini-title">七年级数学 / 单元练习</span><h3>{['每一步，都有据可循。', '这节课，重点讲什么？', '把薄弱处，再练一次。'][mode]}</h3></div><span className="lp-state">{['待老师复核', '示例学情', '练习示例'][mode]}</span></div>
        {mode === 0 ? <div className="lp-paper-grid"><div className="lp-paper"><div className="lp-paper-heading">一元一次方程 · 随堂练习<span>第 03 题 / 共 10 题</span></div><p>解方程：3(x − 2) = 2x + 5</p><div className="lp-handwriting">解：3x − 6 = 2x + 5 <em>✓</em><br />　　3x − 2x = 5 − 6 <em>↙</em><br />　　x = −1</div><div className="lp-red-note">移项时，记得变号。</div><div className="lp-paper-footer">原卷示意 · 非真实学生作业</div></div><div className="lp-score-panel"><span className="lp-mini-title">AI 建议得分</span><div className="lp-score">3<span> / 5 分</span></div><div className="lp-score-row"><span>去括号</span><b>2 / 2</b></div><div className="lp-score-row"><span>移项与合并</span><b className="lp-red">0 / 2</b></div><div className="lp-score-row"><span>解题过程</span><b>1 / 1</b></div><p className="lp-feedback">需关注：常数项移到等号右侧时，应由 −6 变为 +6。</p></div></div>
        : mode === 1 ? <div className="lp-analysis"><div className="lp-analysis-summary"><div><span className="lp-mini-title">本次练习平均分</span><strong>82.5 <small>/ 100</small></strong></div><div><span className="lp-mini-title">优先讲评知识点</span><h4>移项与符号变化</h4><p>示例：12 份作答出现同类错因</p></div></div>{[['去括号', 92], ['移项变号', 62], ['合并同类项', 85]].map(([label, val]) => <div className="lp-chart-row" key={label}><span>{label}</span><div><i style={{ width: `${val}%` }} /></div><b>{val}%</b></div>)}<p className="lp-mini-title">各知识点正确率 · 合成数据</p></div>
        : <div className="lp-practice"><div className="tw-flex tw-items-center tw-justify-between"><h4>移项变号 · 专项巩固</h4><Icon name="print" /></div><p>从一道错题，延伸到一组有针对性的练习。</p>{['2(x − 3) = x + 4', '5x − 8 = 3x + 6', '4(x + 2) = 2x − 6'].map((q, i) => <div className="lp-practice-question" key={q}><span>0{i + 1}</span>{q}<span className="lp-mini-title">解：________</span></div>)}<span className="lp-mini-title">示例题目 · 实际练习可在工作台生成与下载</span></div>}
      </div>
    </div>
    <div className="lp-demo-bottom"><span><Icon name="check" size={15} /> 原卷可追溯</span><span><Icon name="check" size={15} /> 结果可复核</span><span><Icon name="check" size={15} /> 练习可打印</span></div>
  </div>
}

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [plan, setPlan] = useState<string | null>(null)
  return <div className="lp">
    <a className="lp-skip" href="#main">跳到主要内容</a>
    <header className="lp-header"><div className="lp-container tw-flex tw-items-center tw-justify-between tw-gap-4"><Link to="/welcome" aria-label="红笔君首页" className="lp-logo"><Brand size={36} /></Link><nav aria-label="主导航" className="lp-desktop-nav"><a href="#features">产品功能</a><a href="#workflow">使用流程</a><a href="#pricing">方案与定价</a></nav><div className="tw-flex tw-items-center tw-gap-3"><Link className="lp-login" to="/login">登录</Link><Link to="/register" className="lp-button lp-button-primary lp-nav-cta">开始使用 <Icon name="arrow" size={16} /></Link><button type="button" className="lp-menu-button" aria-label="展开或关闭导航" aria-expanded={menuOpen} aria-controls="mobile-nav" onClick={() => setMenuOpen(!menuOpen)} onKeyDown={e => { if (e.key === 'Escape') setMenuOpen(false) }}><Icon name={menuOpen ? 'close' : 'panel'} /></button></div></div>{menuOpen && <nav id="mobile-nav" className="lp-mobile-nav" aria-label="移动导航">{[['features', '产品功能'], ['workflow', '使用流程'], ['pricing', '方案与定价']].map(([id, label]) => <a key={id} href={`#${id}`} onClick={() => setMenuOpen(false)}>{label}</a>)}</nav>}</header>
    <main id="main">
      <section className="lp-hero lp-container"><div className="lp-eyebrow"><span className="lp-live-dot" /> 为每一位认真教学的老师而做</div><h1>少一点伏案批改，<br /><span>多一点教学灵感。</span></h1><p className="lp-hero-copy">从一摞作业，到一目了然的学情。<br className="lp-mobile-break" />让红笔君接住重复工作，<br className="lp-desktop-break" />把时间留给真正需要你的学生。</p><div className="tw-flex tw-flex-wrap tw-justify-center tw-gap-3"><Link to="/register" className="lp-button lp-button-primary">开启我的教学工作台 <Icon name="arrow" size={18} /></Link><a href="#demo" className="lp-button lp-button-secondary"><Icon name="panel" size={18} /> 看看如何工作</a></div><p className="lp-hero-footnote">批量上传 · AI 辅助批改 · 老师自主复核</p><ProductDemo /></section>
      <div className="lp-context lp-container"><span>围绕真实教学，连接每一个环节</span><div><Icon name="users" /> 班级管理</div><div><Icon name="file" /> 作业批改</div><div><Icon name="chart" /> 学情讲评</div><div><Icon name="print" /> 下载打印</div></div>
      <section id="features" className="lp-section lp-container"><div className="lp-section-heading"><div><span className="lp-kicker">DESIGNED FOR TEACHERS</span><h2>不止批得快，<br />更要看得明白。</h2></div><p>从上传到讲评，少一次来回切换。<br />把分散的教学工作，放进一个顺手的工作台。</p></div><div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-2 lg:tw-grid-cols-4 tw-gap-4">{features.map((item, i) => <article key={item.title} className="lp-feature"><div className="tw-flex tw-justify-between tw-items-center"><span className="lp-feature-icon"><Icon name={item.icon} size={25} /></span><span className="lp-feature-number">0{i + 1}</span></div><h3>{item.title}</h3><p>{item.text}</p><span className="lp-feature-tag">{item.tag}<Icon name="check" size={14} /></span></article>)}</div></section>
      <section id="workflow" className="lp-workflow"><div className="lp-container"><span className="lp-kicker">A SIMPLER ROUTINE</span><h2>上手，不必再上一堂课。</h2><div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-8">{[['01', '建好班级，放入作业', '创建班级与作业，录入参考答案，再批量上传试卷。'], ['02', '让 AI 先做，老师再把关', '查看批改进度，对照原卷复核分数与评分依据。'], ['03', '带着学情，走进下一堂课', '梳理共性错题，生成巩固练习，下载材料用于讲评。']].map(([n, title, text]) => <div className="lp-workflow-step" key={n}><span>{n}</span><h3>{title}</h3><p>{text}</p></div>)}</div></div></section>
      <section id="pricing" className="lp-section lp-container"><div className="lp-centered-heading"><span className="lp-kicker">ROOM TO GROW</span><h2>从一份作业开始，<br />找到适合你的使用方式。</h2><p>方案预览 · 正式价格与权益待公布</p></div><div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-5">{[{ name: '初次体验', desc: '先认识你的新教学搭档', price: '注册查看', unit: '账号实际额度', items: ['创建班级与作业', '体验原卷对照与复核', '查看账号月度批改额度'] }, { name: '日常教学', desc: '为持续使用的老师规划', price: '待公布', unit: '个人使用方案', items: ['围绕日常作业批改', '关注持续的学情跟进', '价格与配额以正式发布为准'] }, { name: '教研组', desc: '为更多教学场景预留空间', price: '规划中', unit: '团队使用方案', items: ['面向教研组的使用需求', '团队能力尚未开放', '具体权益将在上线时公布'] }].map((item, i) => <article className={`lp-plan ${i === 1 ? 'lp-plan-featured' : ''}`} key={item.name}>{i === 1 && <span className="lp-plan-label">为日常教学而设计</span>}<h3>{item.name}</h3><p>{item.desc}</p><div className="lp-plan-price">{item.price}<span>{item.unit}</span></div>{i === 0 ? <Link to="/register" className="lp-button lp-button-secondary">创建账号 <Icon name="arrow" size={16} /></Link> : <button type="button" className={`lp-button ${i === 1 ? 'lp-button-primary' : 'lp-button-secondary'}`} onClick={() => setPlan(plan === item.name ? null : item.name)} aria-expanded={plan === item.name} aria-controls={`plan-${i}`}>了解方案 <Icon name="arrow" size={16} /></button>}<ul>{item.items.map(text => <li key={text}><Icon name="check" size={17} />{text}</li>)}</ul>{plan === item.name && <p role="status" className="lp-plan-info" id={`plan-${i}`}>{item.name}尚未开放购买。你可以先创建账号了解现有工作台，当前可用额度以登录后的账号信息为准。</p>}</article>)}</div><p className="lp-pricing-note">本页不收取费用，不代表正式套餐承诺。现有功能与使用额度以实际账号为准。</p></section>
      <section className="lp-faq lp-container"><div><span className="lp-kicker">A FEW ANSWERS</span><h2>你可能还想知道</h2><p>让工具清楚一点，<br />让使用放心一点。</p></div><div>{faqs.map(([q, a]) => <details key={q}><summary>{q}<Icon name="plus" size={18} /></summary><p>{a}</p></details>)}</div></section>
      <section className="lp-final lp-container"><span className="lp-kicker">LESS ROUTINE. MORE TEACHING.</span><h2>下一份作业，<br className="lp-mobile-break" />交给更从容的你。</h2><Link to="/register" className="lp-button lp-button-primary">开始使用红笔君 <Icon name="arrow" size={18} /></Link><span className="lp-final-mark" aria-hidden="true">阅</span></section>
    </main><footer className="lp-footer lp-container"><Link to="/welcome" className="lp-logo"><Brand size={28} /></Link><span>把时间还给教学。</span><div><a href="#features">产品功能</a><Link to="/login">进入工作台 <Icon name="arrow" size={14} /></Link></div></footer>
  </div>
}
