# Project overview — in plain language

*No technical background needed. This explains what the project is, what each
part does, and how a piece of information travels through it.*

---

## 1. What is this?

It is an **automated stock-research assistant**.

Think of a careful analyst who, every trading day:

1. collects fresh share prices,
2. does the usual chart maths on them,
3. checks whether any of your "watch for this" conditions just came true,
4. if one did, writes up a short research note — looking at the charts, the
   company's finances, and any reports or news you've fed it —
5. and emails you that note with a clear **Buy / Hold / Avoid** view.

This project is a team of small software "workers" that do exactly those steps,
on a schedule, without anyone sitting there watching screens.

It does **not** place trades and it does **not** move money. It produces
**information and opinions** for a human to act on.

---

## 2. The big picture

```
   Price data  ─┐
                ├─►  clean it up  ─►  store it  ─►  do the chart maths
   (from files, │
    or a data   │
    provider)   │
                │
   Your rules  ─┘                                         │
   ("tell me when RSI < 30")                              ▼
                                              Did any rule just trigger?
                                                          │
                                                    yes ──┤── no ─►  do nothing, wait
                                                          ▼
                                        A team of AI "analysts" investigates:
                                        • the charts (technical)
                                        • the company accounts (fundamental)
                                        • your documents & news (research)
                                        then a "risk checker" challenges them,
                                        then a "writer" produces the note.
                                                          │
                                                          ▼
                                        A tidy report (web page + chart)
                                                          │
                                                          ▼
                                            Emailed to you as an alert
```

Alongside all of that, there's a **document library**: you drop in annual
reports, quarterly results, announcements, news articles or your own notes, and
the system reads and remembers them so the "research analyst" can quote them
later.

---

## 3. The parts, one by one

| Part | In plain words | Everyday analogy |
| --- | --- | --- |
| **Input connectors** | Pluggable "ways data gets in": an Excel file, a CSV, a PDF, scanned images, a website crawler, or an online API. Add a source once and swap which one you use later — nothing downstream changes. Each connector sends its output to the right place: price/financial tables to the filing cabinet, text/documents to the library. Website and API connectors can log in first (credentials stay in a secure setting, never in the config). | A set of interchangeable delivery vans — post, courier, email — all dropping into the same in-tray. |
| **Sign-in** | You log in with an email and password before you can use the page. Accounts are created on the same screen ("Create account"), or by an admin from the command line. | The staff badge you tap to get through the door. |
| **Inputs page** | After signing in: a simple web page where you can **drag in a file** (Excel/CSV/PDF/image) or **paste a website address to crawl**, without setting anything up in advance. It also lists your saved sources with a "Run now" button. | The front counter where you hand something in by hand instead of posting it. |
| **Normalisation** | Tidies every source into one consistent format (same column names, same date format). | Re-typing messy notes onto a standard form. |
| **Database (with time-series storage)** | The filing cabinet. Keeps all historical prices, company financials, computed numbers, and every past report. | A very organised archive room. |
| **Calculation engine** | Does the standard technical-analysis maths: moving averages, RSI, MACD, volatility, and so on. | An analyst's calculator and chart pack. |
| **Rules / signal engine** | Your "watch list of conditions". You define things like *"price above its 200-day average **and** RSI below 35"*. It checks these every run. | A tripwire that rings a bell when conditions line up. |
| **The AI analyst team** | Five cooperating assistants (see §4). Only wakes up when a rule triggers. | A small research desk that convenes for a meeting. |
| **Report writer & renderer** | Turns the team's findings into a clean web-page report with a price chart. | The person who formats the final PDF. |
| **Notification service** | Sends the report to you. Email today; WhatsApp / Telegram planned. | The mailroom. |
| **Document library (RAG)** | Reads PDFs and notes you provide, and lets the research assistant "look things up" in them. | A librarian who has read every filing and can find the right paragraph. |
| **Scheduler** | The alarm clock. Runs data collection and scans automatically at set times (e.g. every 15 minutes during market hours). | An office manager who starts each task on time. |
| **The API** | The control panel other software (or a future website) uses to add watch-lists, set rules, and trigger a run on demand. | The reception desk that takes requests. |
| **Frontend (website)** | A browser screen. So far just the **Inputs page** above; the dashboards for watch-lists, runs and reports aren't built yet. | The shop window — one shelf stocked, the rest still empty. |

---

### How data actually gets in — two ways

1. **Automatically** — the scheduler runs your saved sources on a timetable
   (e.g. prices every evening, a news site every few hours). Set it once, forget it.
2. **By hand, from the Inputs page** — sign in, then upload a file or paste a
   website address and hit "crawl". Good for a one-off document or a quick check.

Either way the data lands in the same place and is treated identically from then on.

---

## 4. The AI analyst team (what happens when a rule triggers)

They run in order, like a short meeting:

1. **Supervisor** — decides which specialists are needed for this case and in
   what order. (The chairperson.)
2. **Technical analyst** — reads the charts: is the trend up or down, is it
   overbought or oversold, is volume unusual?
3. **Fundamental analyst** — reads the company's latest numbers: is it cheap or
   expensive, is it carrying too much debt, is it profitable? (Skips politely if
   there are no financials on file.)
4. **Research analyst** — searches your document library and news for anything
   relevant: guidance from management, risks, recent announcements. Quotes its
   sources.
5. **Risk checker / critic** — deliberately pushes back: do the analysts
   disagree? Is this a "buy" signal firing at a risky moment? Produces a
   confidence level and a **go / caution / no-go** verdict.
6. **Report writer** — combines everything into the final note with a headline
   recommendation (**Buy / Hold / Avoid**), a short rationale, and the details
   underneath.

**Every step is recorded.** You can always open a past run and see exactly what
each assistant said and why — nothing is a black box.

> If no AI service is connected, the team still runs and still produces a
> structured report, but the wording is placeholder text rather than real
> analysis. Connecting an AI provider is a single setting.

---

## 5. Following one piece of information through

*Example: you want to know when RELIANCE bounces from oversold territory.*

1. **You set a rule** (via the control panel): "RSI below 35 **and** price above
   the 200-day average → tell me (Buy signal)."
2. **Overnight**, the scheduler collects the day's prices and files them.
3. **Next scan**, the calculation engine works out RELIANCE's RSI and averages.
4. The **signal engine** checks your rule. Today RSI is 32 and price is above the
   200-day line → **the rule triggers.**
5. The **AI team convenes**: the technical analyst notes the oversold bounce
   setup; the fundamental analyst says the company looks fairly valued; the
   research analyst quotes a line from the annual report about retail growth; the
   risk checker flags nothing serious and sets confidence to "medium".
6. The **writer** produces a note: **"Buy — medium confidence"** with the
   reasoning and a chart.
7. The **report** is saved and **emailed to you**.
8. Later, you can revisit the run and read every assistant's contribution.

Total human effort: writing the rule once.

---

## 6. What it deliberately does **not** do

- It does **not** buy, sell, or transfer anything. No brokerage connection, no
  money movement.
- It does **not** give personalised financial advice in a regulated sense — it
  produces research opinions for a human to judge.
- It does **not** guarantee accuracy. Signals and AI notes can be wrong; treat
  them as a starting point.

---

## 7. What's working today vs. still to come

**Working now**
- Pluggable input connectors: Excel, CSV, PDF, images (with an OCR add-on), a
  website crawler (can log in), and generic APIs — all feeding the same two
  destinations.
- **Sign-in** (email + password; create an account on the page) protecting the
  Inputs web page: upload a file or paste a URL to crawl, on demand, plus a list
  of saved sources with "Run now".
- Price intake, tidy-up, storage, and all the chart maths.
- Custom rules and the trigger engine.
- The full five-assistant AI team and the recorded audit trail.
- Report generation (web page + chart) and email delivery.
- Automatic scheduling (including per-source schedules for the connectors).
- The control-panel API.
- Reading your PDFs / notes / crawled pages into the document library.

**Still to come**
- The rest of the website/dashboard — watch-lists, run history, reports in the
  browser (only the Inputs page exists today).
- A live, professional-grade market-data feed (currently file-based or a basic
  online snapshot).
- Built-in image OCR (today the OCR step needs an add-on or an external service).
- WhatsApp and Telegram alerts (email works today).
- Login/permissions enforced on every control-panel action.
- Tracking of positions and profit/loss.

---

## 8. Mini-glossary

| Term | Plain meaning |
| --- | --- |
| **OHLCV** | The five daily price numbers: Open, High, Low, Close, and Volume traded. |
| **Indicator** | A number derived from prices to summarise behaviour — e.g. a moving average. |
| **RSI** | "Relative Strength Index", 0–100. Low (~<30) = possibly oversold; high (~>70) = possibly overbought. |
| **MACD** | A momentum indicator built from two moving averages. |
| **Moving average (SMA/EMA)** | The average price over the last N days; smooths out noise to show the trend. |
| **Volatility** | How much the price jumps around. Higher = riskier. |
| **Input connector** | A plug-in that knows how to read one kind of source (Excel, PDF, image, website, API) and hand its contents to the system. |
| **OCR** | "Optical Character Recognition" — turning a picture of text (a scan or screenshot) into actual text the system can read. |
| **Signal / rule** | A condition you define; when it becomes true, the system acts. |
| **RAG / document library** | Technology that lets the AI search your documents and quote them accurately. |
| **Agent** | One of the small AI assistants in the team. |
| **Run** | One full pass of the pipeline for a ticker, start to finish. Every run is saved. |
| **API** | The set of commands other software uses to control the system. |
| **Scheduler (Celery Beat)** | The component that runs tasks automatically at set times. |
| **Ticker** | A stock's short code, e.g. `RELIANCE`, `TCS`. |

---

*For engineers: [TECHNICAL.md](TECHNICAL.md) (what's built and how) and
[WORKFLOW.md](WORKFLOW.md) (how to run and extend it).*
