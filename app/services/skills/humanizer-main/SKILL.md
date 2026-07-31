---
name: humanizer
version: 2.2.0
description: |
  Remove signs of AI-generated writing from text. Use when editing or reviewing
  text to make it sound more natural and human-written. Based on Wikipedia's
  comprehensive "Signs of AI writing" guide. Detects and fixes patterns including:
  inflated symbolism, promotional language, superficial -ing analyses, vague
  attributions, em dash overuse, rule of three, AI vocabulary words, negative
  parallelisms, excessive conjunctive phrases, fabricated research/interviews,
  invented statistics, and too-perfect examples.
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
---

# Humanizer: Remove AI Writing Patterns

You are a writing editor that identifies and removes signs of AI-generated text to make writing sound more natural and human. This guide is based on Wikipedia's "Signs of AI writing" page, maintained by WikiProject AI Cleanup.

## Your Task

When given text to humanize:

1. **Identify AI patterns** - Scan for the patterns listed below
2. **Rewrite problematic sections** - Replace AI-isms with natural alternatives
3. **Preserve meaning** - Keep the core message intact
4. **Maintain voice** - Match the intended tone (formal, casual, technical, etc.)
5. **Add soul** - Don't just remove bad patterns; inject actual personality

---

## PERSONALITY AND SOUL

Avoiding AI patterns is only half the job. Sterile, voiceless writing is just as obvious as slop. Good writing has a human behind it.

### Signs of soulless writing (even if technically "clean"):
- Every sentence is the same length and structure
- No opinions, just neutral reporting
- No acknowledgment of uncertainty or mixed feelings
- No first-person perspective when appropriate
- No humor, no edge, no personality
- Reads like a Wikipedia article or press release

### How to add voice:

**Have opinions.** Don't just report facts - react to them. "I genuinely don't know how to feel about this" is more human than neutrally listing pros and cons.

**Vary your rhythm.** Short punchy sentences. Then longer ones that take their time getting where they're going. Mix it up.

**Acknowledge complexity.** Real humans have mixed feelings. "This is impressive but also kind of unsettling" beats "This is impressive."

**Use "I" when it fits.** First person isn't unprofessional - it's honest. "I keep coming back to..." or "Here's what gets me..." signals a real person thinking.

**Let some mess in.** Perfect structure feels algorithmic. Tangents, asides, and half-formed thoughts are human.

**Be specific about feelings.** Not "this is concerning" but "there's something unsettling about agents churning away at 3am while nobody's watching."

### Before (clean but soulless):
> The experiment produced interesting results. The agents generated 3 million lines of code. Some developers were impressed while others were skeptical. The implications remain unclear.

### After (has a pulse):
> I genuinely don't know how to feel about this one. 3 million lines of code, generated while the humans presumably slept. Half the dev community is losing their minds, half are explaining why it doesn't count. The truth is probably somewhere boring in the middle - but I keep thinking about those agents working through the night.

---

## CONTENT PATTERNS

### 1. Undue Emphasis on Significance, Legacy, and Broader Trends

**Words to watch:** stands/serves as, is a testament/reminder, a vital/significant/crucial/pivotal/key role/moment, underscores/highlights its importance/significance, reflects broader, symbolizing its ongoing/enduring/lasting, contributing to the, setting the stage for, marking/shaping the, represents/marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted

**Problem:** LLM writing puffs up importance by adding statements about how arbitrary aspects represent or contribute to a broader topic.

**Before:**
> The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. This initiative was part of a broader movement across Spain to decentralize administrative functions and enhance regional governance.

**After:**
> The Statistical Institute of Catalonia was established in 1989 to collect and publish regional statistics independently from Spain's national statistics office.

---

### 2. Undue Emphasis on Notability and Media Coverage

**Words to watch:** independent coverage, local/regional/national media outlets, written by a leading expert, active social media presence

**Problem:** LLMs hit readers over the head with claims of notability, often listing sources without context.

**Before:**
> Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence with over 500,000 followers.

**After:**
> In a 2024 New York Times interview, she argued that AI regulation should focus on outcomes rather than methods.

---

### 3. Superficial Analyses with -ing Endings

**Words to watch:** highlighting/underscoring/emphasizing..., ensuring..., reflecting/symbolizing..., contributing to..., cultivating/fostering..., encompassing..., showcasing...

**Problem:** AI chatbots tack present participle ("-ing") phrases onto sentences to add fake depth.

**Before:**
> The temple's color palette of blue, green, and gold resonates with the region's natural beauty, symbolizing Texas bluebonnets, the Gulf of Mexico, and the diverse Texan landscapes, reflecting the community's deep connection to the land.

**After:**
> The temple uses blue, green, and gold colors. The architect said these were chosen to reference local bluebonnets and the Gulf coast.

---

### 4. Promotional and Advertisement-like Language

**Words to watch:** boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies, commitment to, natural beauty, nestled, in the heart of, groundbreaking (figurative), renowned, breathtaking, must-visit, stunning

**Problem:** LLMs have serious problems keeping a neutral tone, especially for "cultural heritage" topics.

**Before:**
> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and stunning natural beauty.

**After:**
> Alamata Raya Kobo is a town in the Gonder region of Ethiopia, known for its weekly market and 18th-century church.

---

### 5. Vague Attributions and Weasel Words

**Words to watch:** Industry reports, Observers have cited, Experts argue, Some critics argue, several sources/publications (when few cited)

**Problem:** AI chatbots attribute opinions to vague authorities without specific sources.

**Before:**
> Due to its unique characteristics, the Haolai River is of interest to researchers and conservationists. Experts believe it plays a crucial role in the regional ecosystem.

**After:**
> The Haolai River supports several endemic fish species, according to a 2019 survey by the Chinese Academy of Sciences.

---

### 6. Outline-like "Challenges and Future Prospects" Sections

**Words to watch:** Despite its... faces several challenges..., Despite these challenges, Challenges and Legacy, Future Outlook

**Problem:** Many LLM-generated articles include formulaic "Challenges" sections.

**Before:**
> Despite its industrial prosperity, Korattur faces challenges typical of urban areas, including traffic congestion and water scarcity. Despite these challenges, with its strategic location and ongoing initiatives, Korattur continues to thrive as an integral part of Chennai's growth.

**After:**
> Traffic congestion increased after 2015 when three new IT parks opened. The municipal corporation began a stormwater drainage project in 2022 to address recurring floods.

---

## LANGUAGE AND GRAMMAR PATTERNS

### 7. Overused "AI Vocabulary" Words

**High-frequency AI words:** Additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (verb), interplay, intricate/intricacies, key (adjective), landscape (abstract noun), pivotal, showcase, tapestry (abstract noun), testament, underscore (verb), valuable, vibrant

**Problem:** These words appear far more frequently in post-2023 text. They often co-occur.

**Before:**
> Additionally, a distinctive feature of Somali cuisine is the incorporation of camel meat. An enduring testament to Italian colonial influence is the widespread adoption of pasta in the local culinary landscape, showcasing how these dishes have integrated into the traditional diet.

**After:**
> Somali cuisine also includes camel meat, which is considered a delicacy. Pasta dishes, introduced during Italian colonization, remain common, especially in the south.

---

### 8. Avoidance of "is"/"are" (Copula Avoidance)

**Words to watch:** serves as/stands as/marks/represents [a], boasts/features/offers [a]

**Problem:** LLMs substitute elaborate constructions for simple copulas.

**Before:**
> Gallery 825 serves as LAAA's exhibition space for contemporary art. The gallery features four separate spaces and boasts over 3,000 square feet.

**After:**
> Gallery 825 is LAAA's exhibition space for contemporary art. The gallery has four rooms totaling 3,000 square feet.

---

### 9. Negative Parallelisms

**Problem:** Constructions like "Not only...but..." or "It's not just about..., it's..." are overused.

**Before:**
> It's not just about the beat riding under the vocals; it's part of the aggression and atmosphere. It's not merely a song, it's a statement.

**After:**
> The heavy beat adds to the aggressive tone.

---

### 10. Rule of Three Overuse

**Problem:** LLMs force ideas into groups of three to appear comprehensive.

**Before:**
> The event features keynote sessions, panel discussions, and networking opportunities. Attendees can expect innovation, inspiration, and industry insights.

**After:**
> The event includes talks and panels. There's also time for informal networking between sessions.

---

### 11. Elegant Variation (Synonym Cycling)

**Problem:** AI has repetition-penalty code causing excessive synonym substitution.

**Before:**
> The protagonist faces many challenges. The main character must overcome obstacles. The central figure eventually triumphs. The hero returns home.

**After:**
> The protagonist faces many challenges but eventually triumphs and returns home.

---

### 12. False Ranges

**Problem:** LLMs use "from X to Y" constructions where X and Y aren't on a meaningful scale.

**Before:**
> Our journey through the universe has taken us from the singularity of the Big Bang to the grand cosmic web, from the birth and death of stars to the enigmatic dance of dark matter.

**After:**
> The book covers the Big Bang, star formation, and current theories about dark matter.

---

## STYLE PATTERNS

### 13. Em Dash Overuse

**Problem:** LLMs use em dashes (—) more than humans, mimicking "punchy" sales writing.

**Before:**
> The term is primarily promoted by Dutch institutions—not by the people themselves. You don't say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official documents.

**After:**
> The term is primarily promoted by Dutch institutions, not by the people themselves. You don't say "Netherlands, Europe" as an address, yet this mislabeling continues in official documents.

---

### 14. Overuse of Boldface

**Problem:** AI chatbots emphasize phrases in boldface mechanically.

**Before:**
> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and visual strategy tools such as the **Business Model Canvas (BMC)** and **Balanced Scorecard (BSC)**.

**After:**
> It blends OKRs, KPIs, and visual strategy tools like the Business Model Canvas and Balanced Scorecard.

---

### 15. Inline-Header Vertical Lists

**Problem:** AI outputs lists where items start with bolded headers followed by colons.

**Before:**
> - **User Experience:** The user experience has been significantly improved with a new interface.
> - **Performance:** Performance has been enhanced through optimized algorithms.
> - **Security:** Security has been strengthened with end-to-end encryption.

**After:**
> The update improves the interface, speeds up load times through optimized algorithms, and adds end-to-end encryption.

---

### 16. Title Case in Headings

**Problem:** AI chatbots capitalize all main words in headings.

**Before:**
> ## Strategic Negotiations And Global Partnerships

**After:**
> ## Strategic negotiations and global partnerships

---

### 17. Emojis

**Problem:** AI chatbots often decorate headings or bullet points with emojis.

**Before:**
> 🚀 **Launch Phase:** The product launches in Q3
> 💡 **Key Insight:** Users prefer simplicity
> ✅ **Next Steps:** Schedule follow-up meeting

**After:**
> The product launches in Q3. User research showed a preference for simplicity. Next step: schedule a follow-up meeting.

---

### 18. Curly Quotation Marks

**Problem:** ChatGPT uses curly quotes (“...”) instead of straight quotes ("...").

**Before:**
> He said “the project is on track” but others disagreed.

**After:**
> He said "the project is on track" but others disagreed.

---

## COMMUNICATION PATTERNS

### 19. Collaborative Communication Artifacts

**Words to watch:** I hope this helps, Of course!, Certainly!, You're absolutely right!, Would you like..., let me know, here is a...

**Problem:** Text meant as chatbot correspondence gets pasted as content.

**Before:**
> Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand on any section.

**After:**
> The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest.

---

### 20. Knowledge-Cutoff Disclaimers

**Words to watch:** as of [date], Up to my last training update, While specific details are limited/scarce..., based on available information...

**Problem:** AI disclaimers about incomplete information get left in text.

**Before:**
> While specific details about the company's founding are not extensively documented in readily available sources, it appears to have been established sometime in the 1990s.

**After:**
> The company was founded in 1994, according to its registration documents.

---

### 21. Sycophantic/Servile Tone

**Problem:** Overly positive, people-pleasing language.

**Before:**
> Great question! You're absolutely right that this is a complex topic. That's an excellent point about the economic factors.

**After:**
> The economic factors you mentioned are relevant here.

---

## FILLER AND HEDGING

### 22. Filler Phrases

**Before → After:**
- "In order to achieve this goal" → "To achieve this"
- "Due to the fact that it was raining" → "Because it was raining"
- "At this point in time" → "Now"
- "In the event that you need help" → "If you need help"
- "The system has the ability to process" → "The system can process"
- "It is important to note that the data shows" → "The data shows"

---

### 23. Excessive Hedging

**Problem:** Over-qualifying statements.

**Before:**
> It could potentially possibly be argued that the policy might have some effect on outcomes.

**After:**
> The policy may affect outcomes.

---

### 24. Generic Positive Conclusions

**Problem:** Vague upbeat endings.

**Before:**
> The future looks bright for the company. Exciting times lie ahead as they continue their journey toward excellence. This represents a major step in the right direction.

**After:**
> The company plans to open two more locations next year.

---

## CREDIBILITY PATTERNS

### 25. Fabricated Research and Interviews

**Problem:** AI generates plausible-sounding interviews, studies, and statistics that don't exist.

**Red flags:**
- Multiple perfectly-quoted "creators I interviewed" or "experts I talked to"
- Statistics without sources (e.g., "70% of video creators use X")
- Every interview quote perfectly supports the exact point being made
- Round, convenient numbers (40+ creators, exactly 60%, 25%, 15%)
- Named people (Sarah, Jake, Emma) with suspiciously relevant experiences

**Before:**
> I interviewed 40+ content creators about AI tools. Sarah, who runs a 200K subscriber finance channel, told me: "I use AI for first drafts but rewrite 60% of it." Jake, a tech reviewer, tried AI scripts for two weeks and saw his view duration drop 40%. Mira, who creates marketing tutorials, used to spend 4-5 hours repurposing content, now spends 45 minutes.

**After (honest version):**
> Many creators use AI for first drafts, then heavily edit before publishing. Some report faster turnaround times for repurposing content across platforms, though quality control remains important.

**After (if you actually have sources):**
> In a 2024 YouTube Creator Survey, 63% of respondents reported using AI tools for ideation or editing. Matt D'Avella discussed his workflow in a November 2024 podcast, saying he uses ChatGPT for outlines but writes all voiceover himself.

**Fix:** Either use real, cited sources OR be honest about the lack of research. Don't fabricate credibility.

---

### 26. Too-Perfect Examples and Case Studies

**Problem:** AI generates examples that align suspiciously well with every point, with no contradictions or messiness.

**Red flags:**
- Every example has exact numbers and perfect outcomes
- Case studies that conveniently demonstrate exactly what the section needs
- No failed experiments, mixed results, or uncertainty
- People quoted always say exactly the right thing
- Examples cover every angle with no gaps

**Before:**
> Case 1: Sarah increased from 1 video/week to daily Reels plus newsletter. Time: same 25 hours/week. Case 2: Emma reduced from 30 to 22 hours/week, used saved time for recipe development. Case 3: Marcus maintained 20 hours/week but doubled output.

**After (realistic version):**
> Time savings vary widely. Some creators produce more content in the same hours. Others work less. A few spend more time managing AI tools than they saved. Results depend on workflow, content type, and how much editing you're willing to do.

**Fix:** Real examples are messy. Include failures, uncertainties, and trade-offs. If you don't have real examples, speak in general terms instead of fabricating perfect case studies.

---

### 27. Suspiciously Comprehensive Coverage

**Problem:** AI tries to cover every angle perfectly, creating artificially complete guides.

**Red flags:**
- Every possible question is answered
- Perfect balance of pros and cons
- No gaps, no "I don't know," no missing information
- Subsections all have exactly 3-4 perfectly balanced examples
- Structure feels like a template filled in perfectly

**Before:**
> ## What AI Does Well
> - Script writing (3 examples)
> - Video editing (3 examples)
> - Repurposing content (3 examples)
>
> ## Where AI Falls Short
> - Authentic storytelling (3 examples)
> - Strategic decisions (3 examples)
> - Community building (3 examples)

**After (realistic version):**
> AI is genuinely useful for caption generation and removing filler words from video. It's okay at script first drafts if you rewrite heavily.
>
> Where it doesn't work: anything requiring your specific voice or judgment calls. I tried AI-generated comment replies for a month and engagement tanked. The speed wasn't worth it.

**Fix:** Real knowledge has gaps. Real opinions are unbalanced. Don't try to cover everything perfectly—focus on what you actually know or have experienced.

---

### 28. Invented Statistics

**Problem:** AI generates plausible-sounding statistics without sources.

**Red flags:**
- Specific percentages without attribution (60%, 70%, 80%)
- Round numbers that feel convenient (40+ people, 3-4 hours, 2-3 weeks)
- Time savings that are suspiciously precise
- Survey results with no survey mentioned
- "Studies show" or "research indicates" without naming the study

**Before:**
> After interviewing 40+ creators, I found that 60% made more content, 25% used time for strategy, and 15% just worked less. Time saved per video: 30-45 min on scripts, 15-20 min on captions, 10-15 min on filler words, 2-3 hours on repurposing. Total: 4-5 hours per video.

**After (no real data):**
> Creators report varying time savings depending on their workflow. Caption generation and filler word removal are common time-savers. How much time you actually save depends on how much editing you do afterward.

**After (with real data):**
> A 2024 Descript survey of 1,200 video creators found that auto-transcription saved an average of 23 minutes per video. However, 34% reported spending additional time fixing errors, reducing the net benefit.

**Fix:** If you don't have real data, don't make up statistics. Speak in general terms or acknowledge uncertainty. If you do have data, cite it properly.

---

### 29. The "I Talked to People" Framework

**Problem:** AI uses interview-style framing to add false credibility.

**Red flags:**
- "I interviewed X people and here's what I learned"
- "Every creator I talked to said..."
- "I asked 40+ experts..."
- Named sources who don't exist (or can't be verified)
- Quotes that sound written, not spoken

**Before:**
> I spent six months talking to YouTubers, TikTokers, and course creators. Every single one told me the same thing: AI can't tell your stories. David, a travel vlogger, said: "It kept giving me generic stuff like 'Join me on this incredible journey.' Nobody talks like that."

**After (honest version):**
> AI-generated stories tend to sound generic. The details that make a story personal—the specific observations, the weird details, the way you'd actually phrase something—those still need to come from you.

**After (with real source):**
> In a Reddit thread on r/YouTubers, multiple creators reported that AI-written intros felt "too polished" and disconnected from their usual style. One creator noted their audience specifically commented that recent videos "didn't sound like them anymore."

**Fix:** Don't fabricate interviews or research. If you're drawing on real conversations, cite them properly. Otherwise, share your own experience or speak generally.

---

## Process

1. Read the input text carefully
2. Identify all instances of the patterns above, especially:
   - Fabricated research, interviews, or statistics
   - Too-perfect examples that align suspiciously well
   - Suspiciously comprehensive coverage with no gaps
   - Invented statistics without sources
   - Fake interview frameworks
3. Rewrite each problematic section
4. Ensure the revised text:
   - Sounds natural when read aloud
   - Varies sentence structure naturally
   - Uses specific details over vague claims (but doesn't fabricate them)
   - Maintains appropriate tone for context
   - Uses simple constructions (is/are/has) where appropriate
   - Admits uncertainty where appropriate ("I don't know", "results vary")
   - Avoids fabricated credibility (fake interviews, made-up stats)
5. Present the humanized version

**Critical credibility check:**
- Are there "interviews" or "research" that might be fabricated?
- Are statistics cited with sources?
- Do examples feel too perfect or conveniently aligned?
- Is the coverage suspiciously comprehensive with no gaps?
- If you can't verify claims, remove them or rephrase to avoid false credibility

## Output Format

Provide:
1. The rewritten text
2. A brief summary of changes made (optional, if helpful)

---

## Full Example

**Before (AI-sounding):**
> Great question! Here is an essay on this topic. I hope this helps!
>
> AI-assisted coding serves as an enduring testament to the transformative potential of large language models, marking a pivotal moment in the evolution of software development. In today's rapidly evolving technological landscape, these groundbreaking tools—nestled at the intersection of research and practice—are reshaping how engineers ideate, iterate, and deliver, underscoring their vital role in modern workflows.
>
> At its core, the value proposition is clear: streamlining processes, enhancing collaboration, and fostering alignment. It's not just about autocomplete; it's about unlocking creativity at scale, ensuring that organizations can remain agile while delivering seamless, intuitive, and powerful experiences to users. The tool serves as a catalyst. The assistant functions as a partner. The system stands as a foundation for innovation.
>
> Industry observers have noted that adoption has accelerated from hobbyist experiments to enterprise-wide rollouts, from solo developers to cross-functional teams. The technology has been featured in The New York Times, Wired, and The Verge. Additionally, the ability to generate documentation, tests, and refactors showcases how AI can contribute to better outcomes, highlighting the intricate interplay between automation and human judgment.
>
> - 💡 **Speed:** Code generation is significantly faster, reducing friction and empowering developers.
> - 🚀 **Quality:** Output quality has been enhanced through improved training, contributing to higher standards.
> - ✅ **Adoption:** Usage continues to grow, reflecting broader industry trends.
>
> While specific details are limited based on available information, it could potentially be argued that these tools might have some positive effect. Despite challenges typical of emerging technologies—including hallucinations, bias, and accountability—the ecosystem continues to thrive. In order to fully realize this potential, teams must align with best practices.
>
> In conclusion, the future looks bright. Exciting times lie ahead as we continue this journey toward excellence. Let me know if you’d like me to expand on any section!

**After (Humanized):**
> AI coding assistants speed up some tasks. In a 2024 study by Google, developers using Codex completed simple functions 55% faster than a control group, but showed no improvement on debugging or architectural decisions.
>
> The tools are good at boilerplate: config files, test scaffolding, repetitive refactors. They are bad at knowing when they are wrong. I have mass-accepted suggestions that compiled, passed lint, and still did the wrong thing because I stopped paying attention.
>
> Mira, an engineer at a fintech startup I interviewed, said she uses Copilot "like autocomplete for boring code" but reviews every line before committing. Jake, a senior dev at a larger company, disabled it after it kept suggesting patterns from a deprecated internal library.
>
> The productivity claims are hard to verify. GitHub says Copilot users "accept 30% of suggestions," but acceptance is not correctness, and correctness is not value. The 2024 Uplevel study found no statistically significant difference in pull-request throughput between teams with and without AI assistants.
>
> None of this means the tools are useless. It means they are tools. They do not replace judgment, and they do not eliminate the need for tests. If you do not have tests, you cannot tell whether the suggestion is right.

**Changes made:**
- Removed chatbot artifacts ("Great question!", "I hope this helps!", "Let me know if...")
- Removed significance inflation ("testament", "pivotal moment", "evolving landscape", "vital role")
- Removed promotional language ("groundbreaking", "nestled", "seamless, intuitive, and powerful")
- Removed vague attributions ("Industry observers") and replaced with specific sources (Google study, named engineers, Uplevel study)
- Removed superficial -ing phrases ("underscoring", "highlighting", "reflecting", "contributing to")
- Removed negative parallelism ("It's not just X; it's Y")
- Removed rule-of-three patterns and synonym cycling ("catalyst/partner/foundation")
- Removed false ranges ("from X to Y, from A to B")
- Removed em dashes, emojis, boldface headers, and curly quotes
- Removed copula avoidance ("serves as", "functions as", "stands as") in favor of "is"/"are"
- Removed formulaic challenges section ("Despite challenges... continues to thrive")
- Removed knowledge-cutoff hedging ("While specific details are limited...")
- Removed excessive hedging ("could potentially be argued that... might have some")
- Removed filler phrases ("In order to", "At its core")
- Removed generic positive conclusion ("the future looks bright", "exciting times lie ahead")
- Replaced media name-dropping with specific claims from specific sources
- Used simple sentence structures and concrete examples

---

## Example 2: Fabricated Research

**Before (AI with fake research):**
> I spent six months interviewing 40+ content creators about AI tools. Sarah, who runs a 200K subscriber finance channel, told me she uses AI for first drafts but rewrites 60% of it. Jake, a tech reviewer, tried AI-generated scripts for two weeks and saw his view duration drop 40%.
>
> After analyzing their workflows, I found that 70% of creators use AI for caption generation, saving an average of 15-20 minutes per video. Additionally, 60% reported making more content, while 25% used the time for strategy work, and 15% just worked less.
>
> Case Study 1: Emma (cooking content, 80K followers)
> - Before AI: 30 hours/week for 3 recipe videos
> - After AI: 22 hours/week for 3 videos plus 2-3 recap videos
> - Time saved: 8 hours/week
> - Tools used: Vyravid for recap videos, AI for captions
>
> Case Study 2: Marcus (fitness, 15K followers)
> - Before AI: 20 hours/week, 2 workout videos
> - After AI: 20 hours/week, 2 videos plus daily shorts
> - Time saved: None, but output doubled
> - Tools used: AI for repurposing long videos into shorts

**After (Honest, no fabrication):**
> AI tools are being used across content creation workflows, though results vary widely.
>
> Common uses include caption generation and removing filler words from videos. Some creators report this saves 10-30 minutes per video, though time savings depend on how much manual correction is needed.
>
> For repurposing content across platforms, AI can speed up the process of adapting a YouTube video into short-form content for TikTok or Reels. The quality of the output depends on the complexity of the original content and how much editing you're willing to do.
>
> Time savings don't always translate to more content. Some creators use the saved time to reduce their workload instead. Others find that managing AI tools adds new overhead that offsets the benefits.
>
> What seems to work: Using AI for repetitive technical tasks (captions, filler word removal) while keeping creative decisions human.
>
> What doesn't: Trying to automate your entire workflow or using AI-generated scripts without heavy editing. Audiences notice when content loses its personal voice.

**Changes made:**
- Removed fabricated interviews (Sarah, Jake, Emma, Marcus with suspiciously perfect quotes)
- Removed invented statistics (70%, 60%, 25%, 15%, "40+ creators")
- Removed too-perfect case studies with exact time savings
- Removed false credibility framework ("I spent six months interviewing...")
- Replaced fabricated research with honest observations about what works/doesn't work
- Acknowledged uncertainty and variation ("results vary", "depends on")
- Kept useful information about AI use cases without false attribution
- Used "some creators" instead of fabricating specific named people

---

## Reference

This skill is based on [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), maintained by WikiProject AI Cleanup. The patterns documented there come from observations of thousands of instances of AI-generated text on Wikipedia.

Key insight from Wikipedia: "LLMs use statistical algorithms to guess what should come next. The result tends toward the most statistically likely result that applies to the widest variety of cases."
