# SEO优化工具（百度 + Google 双引擎）
> 文档版本：V3.0
> 创建日期：2026-09-07
> 最后更新：2026-09-07
> 关联需求：全局
> 文档状态：定稿

## 目的
把静态站的 SEO 优化从"手改N个HTML"变成"改配置+跑一条命令"。七个幂等 Node 脚本 + 一个编排脚本，同时覆盖百度和 Google 两套规则，可直接复制到任意静态站项目。

> V2.0 变更：V1.0 只覆盖百度。实测发现百度那套做完对 Google 基本无增益（keywords 谷歌不看、预渲染谷歌本来就能执行 JS），Google 的权重完全在另一批指标上。本版补齐 Google 侧并给出两套规则的分工。
>
> V3.0 变更：V2.0 是"照着某个站的缺口补脚本"，导致那个站本来就有的项（canonical、结构化数据、懒加载、description）从没实现过——换新项目会**静默失效**。本版补齐这四项脚本，新增 `seo-audit.js` 全站审计（覆盖脚本改不了但必须知道的项：死链、标题层级、内容量等），并把审计接成流水线收尾门禁。第 4 节给出完整覆盖清单，用于确认没有"只写进文档却没脚本管"的项。
>
> **这条教训值得单独记**：按现有项目的缺口来设计工具，会把该项目"恰好已达标"的项误当成"不需要管"。工具的完整性要对照要素清单来验，不能对照某一个站的现状。

配套关系：
- `docs/03-Prompt模板库/Prompt模板库.md` 的**网站SEO现状评估模板**负责"查什么"
- 同库的**双引擎SEO优化执行模板**负责"怎么让AI改"
- 本文档负责"实际怎么改"

来源：军事仿真门户网站项目实战（2026-09-07，26个页面全量落地并验证通过）。

## 1. 两个引擎在意的东西不一样

这是整份文档最关键的一节。**按 Google 那套做完，百度侧可能几乎没有效果；反之也一样。**

| 项目 | Google | 百度 |
|---|---|---|
| JS 渲染 | 基本都会执行 | **基本不执行，只认静态 HTML** |
| keywords 标签 | 2009 年已弃用 | **至今仍参考** |
| title 截断 | 约 600px（较宽松） | PC 约 30 字，移动约 20 字 |
| 设备适配 | 靠 viewport 自动识别 | 需 `applicable-device` 显式声明 |
| 核心排名信号 | **Core Web Vitals**（LCP/CLS/INP）是明确排名因子 | 页面速度有影响但权重低于内容与收录 |
| 收录提速 | 靠 sitemap 与外链自然抓取 | **有主动推送 API，效果显著** |
| 结构化数据 | 富媒体摘要支持成熟 | 支持较弱，但不影响加 |

**分工结论**：
- **百度侧**核心是"能不能被抓到、抓到的内容对不对"——预渲染、keywords、title 长度、主动推送
- **Google 侧**核心是"页面体验好不好"——Core Web Vitals、结构化数据、社交卡片
- 两边共用的：sitemap/robots/canonical、语义化 HTML、alt、h1 唯一性、内容质量

## 2. 优先级

按实测效果排序，不要平铺执行。

### 百度侧

**B0 关键内容是否 JS 注入** —— 若 header/footer/导航靠 JS 生成，百度抓到的每页都是无导航的孤岛，全站内链等于零。实测某项目预渲染后静态内链：首页 12→59 条，产品页 4→51 条。一条压过百度侧其他所有优化项之和。

**B1 百度专有 meta** —— keywords 缺失等于放弃一个百度仍在用的信号；响应式站不声明 `applicable-device` 会影响移动端排名。

**B2 title 格式与长度** —— 超长被截断会让核心词根本显示不出来。

**B3 主动推送 API** —— 百度提速收录最有效的手段，但需上线后在平台侧配置。

### Google 侧

**G0 CLS：图片缺 `width`/`height`** —— 浏览器不知道图片固有尺寸时，图片加载完成的瞬间会把后续内容顶下去，产生布局偏移。CLS 是 Core Web Vitals 三大指标之一、Google 明确的排名因子。实测某项目 911 个 `<img>` 全部缺失，是 Google 侧最大的单项缺口。

**G1 LCP：首屏图发现太晚** —— 若首屏大图是 CSS `background-image`，浏览器必须先下载并解析 CSS 才能发现它，发现时机很晚。用 `<link rel="preload" as="image" fetchpriority="high">` 提到 HTML 解析阶段。

**G2 结构化数据** —— Organization / Product / BreadcrumbList，影响富媒体摘要与点击率。

**G3 图片体积** —— 直接影响 LCP。转 WebP 通常能省 30% 左右（实测数据见第 6 节）。

**G4 社交卡片与 404 页** —— Twitter Card 补齐分享显示；404 页要 `noindex, follow`（不进索引但让爬虫顺着链接回到正常页面）。

### 两边共用

**C0 sitemap（带 lastmod）/ robots.txt / canonical**，以及 URL 规范化（`index.html` 与目录形式不要并存）。

## 3. 自检清单（改之前先跑）

```bash
# 【百度】关键内容是否 JS 注入（最重要，先查这条）
grep -rn 'id="site-header"\|id="site-footer"\|innerHTML\|outerHTML' --include="*.html" .

# 【Google】img 是否缺 width/height（CLS 关键）
echo "img:$(grep -ro '<img ' --include='*.html' . | wc -l) 带width:$(grep -ro '<img [^>]*width=' --include='*.html' . | wc -l)"

# 【Google】结构化数据类型分布
grep -rho '"@type": *"[A-Za-z]*"' --include="*.html" . | sort | uniq -c | sort -rn

# 【Google】首屏图是 img 还是 CSS 背景图（决定要不要 preload）
grep -o "background-image:url('[^']*')" index.html | head -1

# 【Google】图片总体积与格式
du -sh assets/images; find assets/images -name "*.webp" | wc -l

# 【双方】各页标签覆盖
for f in $(find . -name "*.html" -not -path "./.git/*"); do
  echo "$f | title:$(grep -c '<title>' $f) desc:$(grep -c 'name=\"description\"' $f) \
kw:$(grep -c 'name=\"keywords\"' $f) canon:$(grep -c 'rel=\"canonical\"' $f) \
dev:$(grep -c 'applicable-device' $f) h1:$(grep -c '<h1' $f)"
done

# 【百度】title 长度（PC 约 30 字截断）
grep -h "<title>" $(find . -name "*.html") | sed 's/.*<title>//;s/<\/title>//'

# 【双方】sitemap / robots
ls robots.txt sitemap.xml 2>/dev/null; grep -c "lastmod" sitemap.xml 2>/dev/null
```

## 4. 脚本清单与运行顺序

统一放项目根的 `tools/`，全部幂等（靠 HTML 注释标记定位替换区域）。

```
tools/
├─ seo-all.js               ← 一键编排，固化正确顺序，日常只跑这个
├─ seo-audit.js             ← 全站审计（只读）。可单独跑，也是流水线收尾门禁
├─ prerender-partials.js    百度 B0：预渲染 JS 注入的公共部分
├─ seo-meta.js              百度 B1/B2 + 共用：title / description / keywords /
│                           设备声明 / og / canonical（配置表在 PAGES 常量）
├─ google-perf.js           Google G1/G4：首屏图 preload、Twitter Card
├─ gen-structured-data.js   Google G2：BreadcrumbList / Organization / WebSite
├─ add-lazy-loading.js      共用：非首屏图 loading="lazy" + decoding="async"
├─ add-img-dimensions.js    Google G0：img 尺寸属性
├─ gen-robots.js            共用 C0：robots.txt（域名从配置来）
├─ gen-sitemap.js           共用 C0：扫描生成 sitemap
├─ check-html.js            标签配对校验
└─ lib/
   ├─ image-size.js         纯 Node 读图片固有尺寸（无第三方依赖）
   ├─ inject-dimensions.js  尺寸注入的共享实现
   └─ audit-checks.js       审计的各维度检查实现
```

**这套脚本覆盖的完整清单**（对照常被提到的 SEO 要素，确认没有只写进文档却没脚本管的项）：

| 要素 | 负责脚本 | 说明 |
|---|---|---|
| sitemap.xml | `gen-sitemap.js` | 带 lastmod，自动排除 noindex 页 |
| robots.txt | `gen-robots.js` | 域名从配置来，含 Baiduspider/Googlebot 显式段 |
| canonical | `seo-meta.js` | 缺失时**插入**，不只是替换 |
| title | `seo-meta.js` | 百度格式 + 字数告警 |
| description | `seo-meta.js` | 缺失时插入 + 超 80 字告警 |
| keywords / 设备声明 | `seo-meta.js` | 百度专有 |
| og / Twitter Card | `seo-meta.js` + `google-perf.js` | og:image 用绝对 URL |
| 结构化数据 | `gen-structured-data.js` | 从可见面包屑解析，保留手写 Product 等块 |
| 图片懒加载 | `add-lazy-loading.js` | 跳过首屏图与装饰图标 |
| 图片尺寸(CLS) | `add-img-dimensions.js` | 含 `img{height:auto}` 前置检查 |
| 首屏 preload(LCP) | `google-perf.js` | 支持 CSS 背景图 |
| 死链 / alt / h1 / 标题层级 / 内容量 | `seo-audit.js` | 只检不改，改动需人工判断 |

**顺序有依赖，不要手动分开跑**：`prerender` 会重新生成 header/footer，若它不自带尺寸属性，后面必须再跑一次 `add-img-dimensions` 才能补回。本工具的做法是让 `prerender` 直接复用 `lib/inject-dimensions.js`，生成时就带上尺寸——这样单独跑预渲染也不会留下缺尺寸的图标。`gen-sitemap` 放最后，因为 `lastmod` 取文件 mtime。

`seo-all.js` 把这个顺序固化下来，日常只需：

```bash
node tools/seo-all.js
```

## 5. 各脚本要点

完整源码见项目 `tools/` 目录（军事仿真门户网站项目已落地一套可直接复制的实现）。这里只记要点与坑。

### 5.1 prerender-partials.js（百度 B0）

用 `vm.runInContext` 在沙箱里执行 `partials.js`，取出 `renderHeader`/`renderFooter`，按各页 `<body data-base>`/`data-nav` 生成静态 HTML 替换占位 div，用 `<!-- PRERENDER:HEADER:START/END -->` 包裹以支持幂等重跑。

三个必须注意的点：
1. 删 `<script src="partials.js">` 前先确认无其他消费者：`grep -n "NAV_ITEMS\|renderHeader" assets/js/*.js`
2. 原脚本文件**保留在磁盘**作为唯一数据源，只是不再被页面引用
3. **改完 partials.js 必须重跑本脚本**，否则页面导航不会更新——引入预渲染后新增的约束，容易忘

### 5.2 seo-meta.js（百度 B1/B2）

`PAGES` 常量集中管理每页的 title 与 keywords，改文案改这里再重跑，不要手改 HTML（会被下次重跑覆盖）。

- title 用百度官方推荐的 `核心词_修饰词_品牌` 下划线格式，压在 30 字内，脚本自动打印字数并对超长告警
- 写用户真会搜的词，不是内部产品代号（例：硬件页主词用"原子磁强计"而不是产品代号"天磁"）
- `applicable-device` 响应式站填 `pc,mobile`；**不要加 `mobile-agent`**，那是独立 m 站做适配跳转用的，误加会让百度找错移动版
- og 标签在此一并生成，复用已有 description 避免两处维护

### 5.3 add-img-dimensions.js + lib/image-size.js（Google G0）

`lib/image-size.js` 纯 Node 解析 PNG/JPEG/GIF/WebP/SVG 头部读固有尺寸，不依赖第三方库（PNG 读 IHDR 块，JPEG 扫 SOF 帧头，SVG 优先取 width/height 属性、退回 viewBox 宽高比）。实测与 Python PIL 交叉验证结果一致。

**前置条件（关键）**：CSS 里必须有 `img{height:auto}`，否则图片被 `max-width:100%` 压缩时会因固定 height 而变形。脚本启动时会检查这一条，缺失就报错退出而不是继续写坏页面。局部规则里显式写了 `height`（如 `object-fit:cover` 的卡片图）选择器权重更高，不受影响。

### 5.4 google-perf.js（Google G1/G4）

- 取页面第一个 `background-image` 作为首屏图，输出 `<link rel="preload" as="image" fetchpriority="high">`
- Twitter Card 复用已有 og 值
- **`og:image`/`twitter:image` 必须是绝对 URL**，社交平台不解析相对路径。脚本从 canonical 提取 origin 再拼绝对地址；而 `preload` 的 href 要用相对路径（页面自身加载）。两者路径形式不同，容易混

### 5.5 gen-sitemap.js（共用 C0）

扫描实际文件生成，不会漏新页面也不会留已删页面的死 URL。两个要点：
- `lastmod` 取文件 mtime，百度用它判断更新频率
- **自动排除标了 `noindex` 的页面**（如 404）。一边声明"别收录"、一边又提交进 sitemap 是自相矛盾的信号

### 5.6 check-html.js

标签配对校验。预渲染动了每页 DOM 结构，改完必须验。正则用 `<tag(?=[\s>])` 前瞻，既匹配 `<div>` 也匹配 `<div class="x">`，且不会把 `<divider>` 算进来。

### 5.7 gen-structured-data.js（Google G2）

生成 BreadcrumbList / Organization / WebSite，**从页面可见的 `.breadcrumb` 元素解析**——Google 要求结构化数据与用户看到的内容一致，不一致可能被判作弊，所以不能凭文件路径凭空编。

两个关键设计：
- **只删自己负责的类型**。清理旧数据时只移除 `BreadcrumbList`，保留页面上手写的 `Product`/`Service`/`ItemList` 等块，不会把别人的数据洗掉
- 首页已有手写 `Organization` 时不重复生成，避免同类型重复声明

### 5.8 seo-audit.js（只读，覆盖"改不了但必须知道"的项）

有些问题脚本不该自动改——死链要人工判断是删链接还是补页面，内容偏薄要人写内容，标题层级要看样式绑定。这些交给审计报告。

覆盖维度：robots/sitemap 一致性、canonical（含多页指向同一 canonical 的重复内容检查）、title/description 长度与跨页重复、百度专有标签、og/Twitter、h1 唯一性与标题层级连续性、**结构化数据的内容有效性**、图片（alt/尺寸/断链/懒加载）、链接（死链/空链/静态内链数）、性能（preload/渲染阻塞/大图）、正文字数。

输出按 error/warn 分级并**按问题聚合**（25 页同一个问题合成一条，不刷屏）。有 error 时退出码 1，可接进发布检查；`seo-all.js` 会把它当门禁但区分"发现问题"和"脚本崩了"。

**结构化数据必须验内容，不能只验能否解析**——见下面第 10 节第 9 条。

**链接检查的射程边界**（已逐行核对 `lib/audit-checks.js`）：`checkLinks` 只验 `<a href>`、`checkImages` 只验 `<img src>`，**`<link href>`（favicon/css/preload）与 `<script src>` 的存在性不验**；且 `:243` 用 `split('#')[0]` 丢掉锚点，**不校验锚点目标 id 是否存在**。这三类缺口由 `02-工具/静态站链路自查工具.md` 兜住（零依赖 Python 脚本，秒级），两者互补，建议都跑。实战撞过的两例：21 个页面 favicon 路径缺 `../`（两个 check 函数都跳过）、`google-perf.js` 注入的 preload 指向已改名的图片（`checkPerf` 只查有没有 preload 字样，不查指向的文件在不在）。

## 6. WebP 转换：先量化再决定

转 WebP 是 Google 侧收益明确的一项（直接改善 LCP），但要动全部图片文件和 HTML 引用，成本高。**先用脚本量化实际收益再决定做不做**，不要凭"WebP 更好"就上：

```python
from PIL import Image
import os, io, glob
tot_o = tot_w = tot_j = 0; n = 0
for f in glob.glob('assets/images/**/*.jpg', recursive=True) + glob.glob('assets/images/**/*.png', recursive=True):
    if 'backup' in f: continue
    o = os.path.getsize(f)
    try: im = Image.open(f).convert('RGB')
    except: continue
    b = io.BytesIO(); im.save(b, 'WEBP', quality=82); w = b.tell()
    b2 = io.BytesIO(); im.save(b2, 'JPEG', quality=82, optimize=True, progressive=True); j = b2.tell()
    tot_o += o; tot_w += w; tot_j += j; n += 1
print(f"{n} 张位图\n当前 {tot_o/1024/1024:.2f}MB\n"
      f"转WebP {tot_w/1024/1024:.2f}MB (省{(1-tot_w/tot_o)*100:.0f}%)\n"
      f"仅重压JPEG {tot_j/1024/1024:.2f}MB (省{(1-tot_j/tot_o)*100:.0f}%)")
```

某项目实测：218 张位图 10.97MB → WebP 7.72MB（省 30%），仅重压 JPEG 只省 10%。**30% 值得做，10% 不值得动那么多文件。**

判断依据：若量化结果只有 10% 上下，改 N 个文件引用的断链风险不划算，优先做别的；若 30% 以上再考虑。真要做，注意现代浏览器 WebP 支持已接近全覆盖，不一定需要 `<picture>` 回退，但 CSS 背景图可用 `image-set()` 做渐进增强。

## 7. robots.txt 模板

```
User-agent: Baiduspider
Allow: /
Disallow: /tools/
Disallow: /assets/images_original_backup/

User-agent: Googlebot
Allow: /
Disallow: /tools/
Disallow: /assets/images_original_backup/

User-agent: *
Allow: /
Disallow: /tools/
Disallow: /assets/images_original_backup/

Sitemap: https://example.com/sitemap.xml
```

屏蔽构建脚本目录和原图备份目录——这些不该进索引，也白耗抓取配额。

## 8. 实施顺序

```bash
# 0. 备份（静态站往往无版本控制，这步不能省）
D=../_seo_backup_$(date +%Y%m%d)
for f in $(find . -name "*.html" -not -path "./.git/*"); do
  mkdir -p "$D/$(dirname $f)"; cp "$f" "$D/$f"
done
cp assets/css/*.css "$D/"

# 1. 先审计，拿到完整缺口清单（只读，不改文件）
node tools/seo-audit.js --verbose

# 2. 补 CSS 前置条件（add-img-dimensions 的硬性依赖）
#    在样式表里确认有：img { max-width:100%; height:auto; display:block; }
#    需要 .sr-only 补标题层级的话，也在这一步加

# 3. 填配置：tools/seo-meta.js 的 PAGES 表（title/description/keywords/canonical）
#    tools/gen-robots.js 与 gen-sitemap.js / gen-structured-data.js 顶部的 SITE 常量

# 4. 一键跑完（末尾会自动跑审计门禁）
node tools/seo-all.js

# 5. 验证：幂等性（重跑应完全无改动）
node tools/seo-all.js   # 期望所有步骤都是 "0 个文件已更新"

# 6. 验证：关键指标
echo "内链数：$(grep -o '<a ' index.html | wc -l)"                      # 预渲染收益
echo "尺寸覆盖：$(grep -ro '<img [^>]*width=' --include='*.html' . | wc -l)/$(grep -ro '<img ' --include='*.html' . | wc -l)"
grep -rl 'id="site-header"' --include="*.html" . | wc -l                # 应为 0
grep -rn '<script[^>]*partials\.js' --include="*.html" . | wc -l        # 应为 0
```

审计报告里剩下的 warn 要逐条判断该不该修，**不是清零才算合格**——有些项（如压不动的大图）为了它损画质反而是错的。

**第 2 步跑完必须在浏览器实际打开确认交互**（悬浮菜单、移动端汉堡菜单、图片是否变形）。脚本能验证结构和标签，验证不了渲染效果。

## 9. 平台侧接入（代码改完之后）

### 百度搜索资源平台
1. 验证站点（HTML 标签方式最简单）
2. 提交 sitemap
3. **配置普通收录 API 主动推送** —— 百度提速收录最有效的手段：
   ```bash
   curl -H 'Content-Type:text/plain' --data-binary @urls.txt \
     "http://data.zz.baidu.com/urls?site=example.com&token=YOUR_TOKEN"
   ```
   每次改页面推一次，可接进发布流程
4. 抓取诊断 —— 正好验证百度实际抓到的 HTML 里有没有预渲染出来的导航，这是 B0 是否真生效的唯一直接证据

### Google Search Console
1. 验证站点（同样可用 HTML 标签方式）
2. 提交 sitemap
3. **看"网页体验/Core Web Vitals"报告** —— 验证 CLS 与 LCP 是否真的改善了，这是 G0/G1 生效的直接证据
4. 用**网址检查**工具看渲染后的 HTML 与结构化数据识别结果
5. **富媒体搜索结果测试** 验证 Organization/Product/BreadcrumbList 是否被正确解析

### 服务器侧
- www 与非 www 的 301
- 配置 404 页返回真正的 404 状态码（不是 200，否则搜索引擎会当正常页面收录）
- 启用 gzip/brotli 压缩与静态资源强缓存（间接改善 LCP）

**前置条件**：境内域名未做 ICP 备案，百度收录和排名会明显受压制，这条绕不过。

## 10. 踩过的坑

1. **先确认哪个文件真的在被引用**。某项目 `assets/js/` 下同时有 `partials.js`（368 行，在用）和 `partials-v2.js`（226 行，零引用死代码），文件名带 v2 的反而是旧的。基于旧文件做出的诊断结论全部作废。改之前先 `grep -ho 'partials[^"]*\.js' *.html | sort | uniq -c`。

2. **含正则的校验脚本不要用 `node -e` 内联写**。bash 双引号会吃掉转义，`[\\\\s>]` 最终变成 `[s>]`，只匹配无属性标签（`<dd>` 匹配到、`<dd class="x">` 漏计），误报了 151 处标签不配对。写成 `.js` 文件再 `node file.js`。

3. **溯源注释会污染 grep 校验**。生成块的注释里若写了 `partials.js` 这类字符串，`grep -rl "partials.js"` 会把注释算成残留引用。校验残留 script 标签要用 `grep -rn '<script[^>]*partials\.js'` 精确匹配标签形式。

4. **`applicable-device` 别写错值**。响应式站填 `pc,mobile`；`mobile-agent` 是独立 m 站用的，误加有害。

5. **加 `width`/`height` 前必须先有 `img{height:auto}`**。否则图片被 `max-width:100%` 压缩时会因固定 height 变形。把这个检查做进脚本，缺失就退出，别让它写坏 900 个标签再回滚。

6. **首屏大图可能是 CSS 背景图而不是 `<img>`**。这种情况 CLS 不受影响（背景图不参与布局偏移），但 LCP 受影响更大（发现时机更晚），要用 preload 而不是找 img 标签加尺寸。查之前先确认首屏图的实现方式。

7. **预渲染会成倍放大 img 数量，要重新核算懒加载**。若导航菜单里有图标，预渲染后每页都会多出一批静态 `<img>`（实测某项目每页 +29 个，全站从 157 涨到 882）。是否补 `loading="lazy"` 按实际收益判断，别机械套"非首屏图片一律 lazy"：
   - 先看去重后的**唯一文件数与总体积**（实测那 29 个只对应 19 个唯一 SVG、合计 8.8KB，全站共用，第二页起就是缓存命中）
   - 再看菜单**显隐方式**：`display:none` 的可以放心加；`opacity`/`visibility:hidden` 的元素仍在视口内，加 lazy 后行为不确定，若真延迟到 hover 才加载会出现首次悬浮图标闪白，UX 损失是实际的而带宽收益接近零
   - 装饰性图标用 `alt=""` 是正确做法，不算 alt 缺失

8. **脚本间的执行顺序会互相覆盖**。预渲染重新生成 header 会冲掉里面 img 的尺寸属性。靠"记得按顺序跑"不可靠——正确做法是把尺寸注入抽成共享模块让预渲染自己调用，从根上消除顺序依赖，再用编排脚本固化顺序。判断标准是**重跑整条流水线应该零改动**；若每次重跑都显示"N 个文件已更新"，说明脚本间存在互相覆盖（churn），要修。

9. **结构化数据"能解析"不等于"有效"，审计必须验内容**。某项目 19 个页面的 BreadcrumbList 全是坏的：`name` 字段里塞的是 HTML 碎片（`"<a href=\".."`、`"index.html\">首页<"`、`"a>"`），每级 `item` 还都指向同一个 URL——像是当初用正则按 `>` 切分面包屑 HTML 生成的。因为 `JSON.parse` 能通过，早期审计把它当成了达标项，还在报告里写成"19 页已有 BreadcrumbList"这种正面结论。
   **验内容至少要覆盖**：字段值里是否混入 HTML 碎片（`[<>]`、`href=`、`.html`）、各级 `item` 是否全指向同一 URL、`position` 是否从 1 连续递增、必填字段（Organization 的 name/url、Product 的 name）是否齐全、URL 是否绝对路径。
   更普适的教训：**任何"生成后没人读"的机器产物都要验语义，不只验语法**。

10. **改标题层级前先查样式绑定**。CSS 里 `h1~h3` 各有 `font-size`、h4 没有，还有 `.product-card h3`、`.ad-title h4` 这类作用域选择器——直接改标签会改变视觉。三种处理方式按情况选：
    - 缺中间级 → 插入 `.sr-only` 的 h2（**不能用 `display:none`/`visibility:hidden`，那样屏幕阅读器也读不到，等于没补**；要用裁剪成 1px 的标准无障碍写法）
    - 必须改标签 → 同步加作用域 CSS 把字号覆盖回原值，保证语义修正不改外观
    - 是导航分组标签而非内容标题（如页脚栏目名）→ 改成 `div` 更准确，顺带消除全站跳级根因
    另外要注意：**页脚里的标题会参与每一页的层级序列**，正文最后一级是 h1 的页面（如 404）会因此被判跳级，排查时别只看正文。

11. **重压缩不一定更小，WebP 也不是每张都省**。某项目两张 1440×810 的 hero banner，按 q82 重压反而**变大 4%**（原图已是更高效的压缩），WebP 也**大 1%**；降到 q60 才省 23%，但已到可见伪影边缘。同项目聚合数据是"WebP 省 30%"，实际是 212/218 张更小、6 张更大——**聚合收益不能当成每张都成立**。逐张核算，压不动的就别为一条 warn 损画质。

## 11. 合规提醒（涉密/敏感行业必读）

做 SEO 本质是**主动把内容推向公开索引**，方向和信息管控相反。涉军工、医疗、金融等敏感行业时，在配主动推送**之前**必须逐页确认哪些内容适合进公开索引：

- 不适合的页面加 `<meta name="robots" content="noindex">`，比收录后再提交死链干净得多（`gen-sitemap.js` 会自动排除这些页面）
- 涉具体项目/客户名称、量化效能数据、内部技术指标的页面重点排查
- keywords 与 title 的措辞同样要过一遍：同一个产品往往可以用民用技术表述替代敏感表述（如用"原子磁强计、磁异常探测、量子传感"而不做军事化措辞），既合规又不损失搜索覆盖，因为客户搜的本来就是这些技术名词
