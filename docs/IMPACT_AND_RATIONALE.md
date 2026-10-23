# MediDispatch GH: Why Ghana Needs It, and Why It Uses an Open-Weight AI Model

*Research brief, October 2026. Every figure is cited; numbered sources are listed at the end. Where sources disagree, both are shown.*

---

## Key numbers at a glance

| | Figure | Source |
|---|---|---|
| Road crash deaths officially recorded, 2024 | **2,494** (≈ 7 a day), plus **15,607** injured | NRSA via GNA [1] |
| WHO's modelled estimate of real road deaths, 2021 | **8,494**, about **3×** the official count | WHO [2] |
| Ghana's road death rate vs Africa and the world | **≈ 26** per 100,000 vs **19** (Africa) and **15** (global) | WHO [3] |
| Trauma deaths judged preventable (Komfo Anokye study) | **60%** (23% definitely + 37% potentially) | Yeboah et al. [6] |
| Leading care failure in those preventable deaths | **Pre-hospital delay: 44%** | Yeboah et al. [6] |
| National ambulance response time, 2025 | **26 min 23 s** against a 20-minute target | NAS via Ghanaian Times [7] |
| Emergency calls NAS did not respond to, 2025 | **5,315** of 42,154 (**12.6%**) | NAS via Ghanaian Times [7] (calculated) |
| Ambulance trips that were hospital-to-hospital transfers, 2022 | **81.3%** | Zakariah et al. [8] |
| Ambulances serving all of Greater Accra, June 2025 | **≈ 42** | NAS Greater Accra Dispatch Head [9] |
| Ambulances out of service, February 2026 | **127 of 318** (40%) | NAS clinical auditor, cited in [10] |
| Calls to 112 that were pranks (Jan–Mar 2020) | **99.17%** (1,887,125 of 1,902,926) | Ministry of Communications [11] |
| Women who died in childbirth in health facilities, 2025 | **958** | Ghana Health Service [12] |
| Internet users / mobile connections | **74.6%** of people online; **41.8 million** mobile connections (**119%** of population), **96%** of them 3G/4G/5G | DataReportal 2026 [14] |
| March 2024 subsea cable cut | All **4** cables linking Ghana to Europe down; NCA estimated **≈ 5 weeks** to restore | NCA [15], Semafor [16] |
| AI model size on disk (Llama 3.2 3B, 4-bit) | **2.02 GB**; runs on an ordinary server CPU | Hugging Face [19] |

---

## 1. The problem: in Ghana, the gap between injury and care kills

### 1.1 Road crashes are a growing national emergency

- **2,494 people died and 15,607 were injured in 13,489 road crashes in 2024**, up from 2,276 deaths in 2023 [1]. That is about **7 deaths and 43 injuries every day** (2,494 ÷ 366; 15,607 ÷ 366).
- The trend is worsening. In the first half of 2025 recorded crashes rose to 7,289 (from 6,653 in the same period of 2024) and injuries to 8,364 (from 7,561) [1]. First-quarter 2025 deaths were **752, up 23.5%** on the 609 in Q1 2024 [1]. The National Road Safety Authority (NRSA) warned of **up to 3,000 deaths** in 2025 [1].
- **Official figures undercount.** WHO's modelled estimate for 2021 is **8,494 road deaths** (95% CI 7,447–9,540), against **2,890** officially reported for 2020 [2]. On WHO's estimate, the true toll may be close to **three times** what is recorded.
- WHO reports that Ghana's road deaths **rose 65% between 2016 and 2021**, and that its rate of nearly **26 deaths per 100,000** is well above the African Region average of **19** and the global average of **15** [3].
- **Who dies:** about one-third are motorcycle riders [3]; WHO's 2023 profile attributes roughly **31% of deaths to pedestrians** and **33% to powered two- and three-wheelers** [2]. In Q1 2025 alone, **116 children under 18** died on the roads [1].
- **Cost:** road crashes are estimated to cost Ghana **over US$230 million a year, about 1.7% of GDP** [1]. (The article does not name the source of this estimate, so treat it as indicative.)

### 1.2 Many of these deaths are preventable, and delay is the biggest reason

- A panel review of trauma deaths at **Komfo Anokye Teaching Hospital, Kumasi** judged **23% definitely preventable and 37% potentially preventable**: 60% in total [6].
- In those preventable deaths, the most common failure was **pre-hospital delay (44%)**, ahead of treatment delay (32%) and inadequate fluid resuscitation (22%). Haemorrhage was the leading cause among definitely preventable deaths (47%) [6].
- In Greater Accra, the National Ambulance Service's mean **response time was 16.9 minutes** against a national 8-minute target, and the **median transport time was 82 minutes**. The authors concluded the service could not meet the "golden hour" guideline [5].

**What this means for MediDispatch:** most of what kills people is time. Every minute saved in finding the patient, deciding how sick they are, and choosing a hospital that can treat them is the system's core value.

### 1.3 The ambulance service is stretched, and much of its capacity is not reaching emergencies

The National Ambulance Service (NAS) has grown impressively, from **9 ambulances and 64 technicians in 2004 to 356 ambulances and 3,473 EMTs**, with a station in all **261 districts** [8]. But:

- **Capacity is thin:** about **1.13 ambulances per 100,000 people** (2022) [8]. Greater Accra, the most populous region, had **about 42 ambulances** available in June 2025, and the dispatch head described rationing them for the most severe cases [9].
- **Many vehicles are off the road:** in February 2026 an NAS clinical auditor reported **127 of 318 ambulances out of service**, leaving 191 operational [10].
- **Responses are slow and some calls go unanswered:** in 2025 NAS received **42,154 emergency calls and responded to 36,839**; the average response time was **26 minutes 23 seconds**, above the 20-minute target [7]. That leaves **5,315 calls (12.6%)** without a response (calculated).
- **Most trips are not emergencies at the scene:** in 2022, **81.3% of ambulance transports were transfers between health facilities** [8]. Transports also vary widely by region, from **0.16 to 0.50 per 100,000 people per day**, with the poorest, most remote regions lowest [8].
- **Help is coming, but needs coordination:** NAS plans to buy **400 new ambulances** and deploy **500 rapid motorbike response units** [7]. More vehicles only save lives if they are dispatched to the right place, quickly, and sent on to a hospital that can take the patient.

### 1.4 The 112 line is flooded with prank calls

Between 28 January and 16 March 2020, Ghana's 112 centre received **1,902,926 calls, of which 1,887,125 (99.17%) were pranks**; only **15,801 were genuine** [11]. The Ghana National Fire Service still logged **131,862 prank calls in Q1 2025** (down 31.5% from 192,545 in Q1 2024) [13]. Every prank call ties up a dispatcher while a real patient waits.

### 1.5 Patients die moving between hospitals that have no bed

"No bed syndrome" has repeatedly been fatal in Ghana. Reported cases include [17]:

- a 29-year-old hit-and-run victim in Accra who died after **nearly three hours** being turned away from **three hospitals** for lack of beds;
- a 70-year-old man who died in his car in 2018 after being refused by **six or seven** Accra hospitals;
- a patient at Tamale Teaching Hospital in April 2025 who arrived to find **all four ICU beds serving the Northern Region** full.

Without a live view of which hospital has a free bed and the right specialist, crews drive from door to door.

### 1.6 Maternal deaths remain stubbornly high

- **958 women died giving birth in Ghana's health facilities in 2025**, an institutional ratio of about **122 per 100,000 live births** [12]. (GHS reported 110 for 2024 and 109 for 2023; these count facility deaths only.)
- The Global Burden of Disease 2023 study estimates Ghana's overall maternal mortality ratio at **275 per 100,000 live births**, with **haemorrhage the leading cause** [18].
- Haemorrhage kills in hours, so delays in reaching a facility with blood and an obstetrician matter as much here as in trauma.

### 1.7 Bystanders are the real first responders, and they can be helped

- Most injured people in Ghana have historically reached hospital in **taxis, buses and private cars**, not ambulances [4].
- In a Ghanaian programme that gave **335 commercial drivers a 6-hour first-aid course**, the share who controlled external bleeding at crashes rose from **4% to 42%**, and who managed the airway from **2% to 35%** [4]. Ordinary people act when they know what to do.

### 1.8 The phones are already in people's pockets

- **74.6% of Ghanaians use the internet**; there are **41.8 million mobile connections (119% of the population)**, and **96%** of them are 3G, 4G or 5G [14].
- That makes a no-install web app (PWA) reachable by most bystanders, while the remaining quarter offline is why MediDispatch always keeps a one-tap **"Call 112"** button and why an SMS/USSD channel is the recommended next step.

---

## 2. How MediDispatch answers each problem

| Problem (evidence) | What MediDispatch does |
|---|---|
| Pre-hospital delay causes 44% of preventable trauma deaths [6] | One button sends the bystander's **GPS location every 10 seconds** straight to crews; paramedics see distance and can navigate immediately. |
| Ambulances rationed; 12.6% of calls unanswered [7][9] | A **live feed of bystander reports** sorted by distance lets the nearest crew **claim** a case in one tap (first claim wins, so two crews never chase the same patient). Severity scoring helps dispatchers send scarce vehicles to the sickest first. |
| 99% of 112 calls were pranks [11] | Every report carries a **name, callback number and GPS**, is **rate-limited per network address**, and can be cancelled by the reporter before a crew is committed. Dispatchers can verify before sending an ambulance. |
| Patients die searching for a bed [17] | Hospitals publish **ER, ICU and ward beds and on-duty specialists in real time**. Matching ranks hospitals by travel time **and** capability, skips full hospitals, and warns when capacity data is stale. |
| Haemorrhage is the leading killer in trauma and childbirth [6][18] | Matching prefers hospitals with a **blood bank, trauma surgeon, obstetrician or maternity unit** depending on the situation; the receiving hospital is **pre-alerted** with vitals before arrival. |
| Bystanders act when guided [4] | The civilian app shows **plain-language first-aid steps** for 12 situations while help is on the way, and they work **with no internet** (cached on the phone). |
| Patient data is sensitive under Ghanaian law [20] | Names, phones, GPS, vitals and photos are **encrypted in the database**; every view is **audited**; photos auto-delete after **30 days**. |
| Patchy connectivity and power [15][21] | Reports queue and retry offline, screens fall back to polling, and **the AI runs locally**, so triage never depends on an international link. |

---

## 3. Why an open-weight AI model, run locally in Ghana

### 3.1 What the AI does, and what it is not allowed to do

The AI is a **recommendation engine, not a diagnostic tool**. Its role is narrow:

1. The system first computes the **Modified Early Warning Score (MEWS)** from vital signs. MEWS is a simple bedside score; in its original validation, a score of 5 or more meant a **5.4-times higher odds of death** and **10.9-times higher odds of ICU admission** [22].
2. The AI (Llama 3.2 3B) reads the vitals **and the free-text symptoms** that MEWS cannot use (for example "crushing chest pain" or "pregnant, heavy bleeding") and suggests a severity and immediate actions in strict JSON.
3. **The AI may raise the severity but can never lower it.** The final severity is always the higher of the two.
4. If the model is offline, slow or returns anything malformed, the system silently uses the MEWS result. In testing, this fallback returned a result in **0.02 seconds**.

**Why "raise only"?** The evidence says language models are not safe to trust alone in triage:

- In a *Nature Medicine* study of **2,400 real patient cases** with common abdominal complaints, every LLM tested **performed significantly worse than physicians**, did not follow guidelines and often ignored instructions [23].
- ChatGPT reached **76.6% overall triage accuracy** against an expert committee in a 2024 study [24]: useful, but wrong roughly one time in four.
- The best model in a 2026 French emergency department study still **under-triaged 4.6%** of patients, showed severe overfitting, and was judged by its own authors **"not ready for clinical use"** [25].

**Why not MEWS alone?** MEWS is transparent and fast, but imperfect. In a 2024 study of **2,797 febrile adults** in Malawi, Mozambique, Zimbabwe and Laos, MEWS predicted 28-day death with an AUROC of only **0.67** [26]. It ignores the history and symptoms a paramedic hears. The AI adds that context in the one direction that is safe: more caution, never less. (The same study found the Africa-derived **UVA score** performed better, at 0.82, a strong candidate for a future version.)

### 3.2 Why open-weight and local rather than a cloud AI service

**1. It keeps working when the internet doesn't.**
On **14 March 2024**, damage to the **ACE, MainOne, SAT-3 and WACS** subsea cables left Ghana's cable landing providers **"completely cut off from international data services"** [15]; the NCA estimated about **five weeks** for full restoration [16]. A triage system that depends on a foreign cloud AI would have lost its AI for the duration. A model running on a server in Ghana is unaffected; and if even that server fails, MEWS takes over.

**2. Patient data never leaves Ghana.**
- Ghana's **Data Protection Act, 2012 (Act 843)** classes **health as special personal data** and requires appropriate technical and organisational security [20]. It contains **no specific rules for transferring data abroad** [20], so the safest design is simply not to send it.
- Health-data sovereignty is now national policy in practice: on **28 April 2026** Ghana **walked away from a US$109 million US health agreement** over reported demands for sensitive health data and access to the GhanaCard database [27]. Commentators also point to the US **CLOUD Act (2018)**, which can compel US companies to hand over data stored abroad [27].
- With a local open-weight model, symptoms and vitals are processed **on hardware the Ministry controls**. Meta describes the Llama 3.2 small models as suited to applications "where data never leaves the device" [28].

**3. It matches Ghana's national AI direction.**
Ghana launched its **National AI Strategy 2025–2035** in April 2026 with a **US$250 million AI Computing Centre**. President Mahama said: *"We must not only use AI, we must localise AI"* and *"We must invest in local data ecosystems"* [29]. A locally hosted open model is exactly that kind of localised AI, and it could run on that national compute.

**4. It is affordable and predictable.**
- No per-request fees, no foreign-currency bills, no vendor that can change prices or shut off access.
- The 4-bit model file is **2.02 GB** (full precision 6.43 GB) [19], small enough for an ordinary CPU server in a regional data centre; no specialist GPU is required.

**5. It can be inspected, tested and adapted.**
- Open weights can be **audited and evaluated on Ghanaian cases** before deployment, and fine-tuned later on local data (for example common presentations or local terms), all without sending anything abroad.
- The harness is **model-agnostic**: changing one setting (`OLLAMA_MODEL`) swaps in another open model if a better or more permissively licensed one is validated.

### 3.3 Why Llama 3.2 3B specifically

| Property | Detail |
|---|---|
| Released | 25 September 2024 by Meta [28] |
| Size | 3 billion parameters; **2.02 GB** at 4-bit (Q4_K_M) [19] |
| Context window | 128,000 tokens [28] |
| Designed for | On-device / edge use; Meta reports the 3B model beats Gemma 2 2.6B and Phi-3.5-mini on instruction following, summarisation and tool use [28] |
| Structured output | Served through Ollama with a JSON schema, so replies can be strictly validated |

### 3.4 Honest caveats

- **"Open-weight" is not "open source."** Llama 3.2 is released under the **Llama 3.2 Community License**, not an OSI open-source licence. It requires a **"Built with Llama"** notice [30]; MediDispatch displays this on the admin AI panel and in the README.
- Meta's **Acceptable Use Policy** prohibits the *unlicensed* practice of medicine [30]. MediDispatch is decision support for **licensed paramedics and clinicians**, but the Ministry's legal team should confirm this reading before deployment.
- The model has **not yet been evaluated on Ghanaian patients**. Before go-live it should be tested on a representative set of local cases, and the rate at which it raises severity should be monitored.
- Llama 3.2 supports **8 languages officially** [30], none of them Ghanaian. Paramedics enter symptoms in English, so this does not block the current design, but bystander-facing AI in Twi, Ewe, Ga or Dagbani would need a different model or further work.

---

## 4. Summary for decision-makers

- Ghana records **about 7 road deaths a day**, WHO estimates the true number may be **three times higher**, and **six in ten** reviewed trauma deaths at a major teaching hospital were judged preventable, with **pre-hospital delay** the main cause.
- The ambulance service is growing but stretched: **26-minute** average responses, **12.6%** of calls unanswered, **40%** of the fleet off the road in early 2026, and most trips used for transfers rather than emergencies.
- MediDispatch connects the three people who decide whether a patient lives (the **bystander**, the **paramedic** and the **receiving hospital**) in real time, so the nearest crew is sent, the sickest patients are seen first, and nobody drives from hospital to hospital looking for a bed.
- Its AI is deliberately constrained: a **local, open-weight model** that keeps patient data in Ghana, keeps working through international outages, costs nothing per use, and **can only make the system more cautious, never less.**

---

## Sources

1. Ghana News Agency, "Ghana's Killer Roads: A National Tragedy" (citing National Road Safety Authority data), 15 Aug 2025. https://gna.org.gh/2025/08/ghanas-killer-roads-a-national-tragedy/
2. WHO, *Global status report on road safety 2023*, Ghana country profile. https://cdn.who.int/media/docs/default-source/country-profiles/road-safety/road-safety-2023-gha.pdf
3. WHO, "Ghana's new road traffic law and safety standards will save lives", 30 Apr 2026. https://www.who.int/news/item/30-04-2026-ghana-s-new-road-traffic-law-and-safety-standards-will-save-lives
4. Mock CN, Tiska M, Adu-Ampofo M, Boakye G. "Improvements in prehospital trauma care in an African country with no formal emergency medical services." *Journal of Trauma* 53(1):90–97, 2002. https://swov.nl/en/publicatie/improvements-prehospital-trauma-care-african-country-no-formal-emergency-medical
5. Mahama M-N, Kenu E, Bandoh DA, Zakariah AN. "Emergency response time and pre-hospital trauma survival rate of the national ambulance service, Greater Accra (January – December 2014)." *BMC Emergency Medicine* 18:33, 2018. https://link.springer.com/doi/10.1186/s12873-018-0184-3
6. Yeboah D, Mock C, Karikari P, Agyei-Baffour P, Donkor P, Ebel B. "Minimizing preventable trauma deaths in a limited-resource setting: a test-case of a multidisciplinary panel review approach at the Komfo Anokye Teaching Hospital in Ghana." *World Journal of Surgery* 38(7), 2014. PMID 24449414.
7. Ghanaian Times, "NAS set to deploy 500 RMUs nationwide" (NAS 2025 Annual and 2026 Mid-Year Performance Review), 16 Jul 2026. https://ghanaiantimes.com.gh/nas-set-to-deploy-500-rmus-nationwide/amp/
8. Zakariah AN, Boateng E, Achena C, Ansong-Bridjan F, Mock C. "The National Ambulance Service of Ghana: Changes in capacity and utilization over 20 years." *African Journal of Emergency Medicine* 14(3):172–178, 2024. https://doaj.org/article/f1a2df15e16a4ba6939b214744822db8
9. Citi Newsroom, "Only 42 ambulances serving Greater Accra — Dispatch Head reveals", 6 Jun 2025. https://citinewsroom.com/2025/06/only-42-ambulances-serving-greater-accra-dispatch-head-reveals/
10. Addae Mensah N. "When enough ambulances isn't enough", *Ghanaian Times*, 2026 (citing an NAS clinical auditor's figures reported to Citinewsroom). https://ghanaiantimes.com.gh/when-enough-ambulances-isnt-enough/amp/
11. Ghanaian Times, "Emergency call centre receives over 1.8m prank calls in 3 months" (Ministry of Communications statement), 27 Mar 2020. https://ghanaiantimes.com.gh/emergency-call-centre-receives-over-1-8m-prank-calls-in-3-months/amp/
12. Ghanaian Times, "1,000 women die during childbirth last year – GHS" (Dr Kennedy Brightson, Ghana Health Service), 12 Mar 2026. https://ghanaiantimes.com.gh/1000-women-die-during-childbirth-last-year-ghs/
13. Ghana News Agency, "GNFS receives 131,862 prank calls in first quarter of this year", 12 May 2025. https://gna.org.gh/2025/05/gnfs-receives-131862-prank-calls-in-first-quarter-of-this-year/
14. DataReportal, "Digital 2026: Ghana", 8 Nov 2025. https://datareportal.com/reports/digital-2026-ghana
15. National Communications Authority, "Update 3: Undersea Cable Disruptions Affect Data Services", 15 Mar 2024. https://nca.org.gh/?p=15858
16. Semafor, "Damaged undersea cables disrupting Africa's internet will take weeks to repair", 18 Mar 2024. https://www.semafor.com/article/03/18/2024/africas-damaged-undersea-cables-disrupt-internet-for-weeks
17. Ghanaian Times, "No bed, no chance: the tragic toll of Ghana's no-bed syndrome", 26 Feb 2026. https://ghanaiantimes.com.gh/no-bed-no-chance-the-tragic-toll-of-ghanas-no-bed-syndrome
18. Ghana News Agency, "Ghana makes gains in maternal mortality ratio, though slowly" (IHME Global Burden of Disease 2023), 4 Apr 2026. https://gna.org.gh/2026/04/ghana-makes-gains-in-maternal-morality-ratio-though-slowly/
19. Hugging Face, bartowski/Llama-3.2-3B-Instruct-GGUF (quantised file sizes). https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF
20. Data Protection Africa, "Ghana Factsheet" (summary of the Data Protection Act, 2012, Act 843), 2019. https://dataprotection.africa/wp-content/uploads/2019/10/Ghana-Factsheet.pdf
21. Citi Newsroom, "Dumsor: Parliament's Mines and Energy Committee orders ECG to issue timetable", 8 Apr 2024. https://www.citinewsroom.com/2024/04/dumsor-parliaments-mines-and-energy-committee-orders-ecg-to-issue-timetable/
22. Subbe CP, Kruger M, Rutherford P, Gemmel L. "Validation of a modified Early Warning Score in medical admissions." *QJM* 94:521–526, 2001. https://cdn2.podiatry.com/eZineImages/PracticePerfect/889/Validation-of-a-modified-Early-Warning-Score-in-medical-admissions.pdf
23. Hager P, Jungmann F, Holland R, et al. "Evaluation and mitigation of the limitations of large language models in clinical decision-making." *Nature Medicine* 30(9):2613–2622, 2024 (summary via AHRQ PSNet). https://psnet.ahrq.gov/issue/evaluation-and-mitigation-limitations-large-language-models-clinical-decision-making
24. Colakca C, et al. "Emergency department triaging using ChatGPT based on emergency severity index principles: a cross-sectional study." *Scientific Reports* 14, 2024. https://doaj.org/article/023c66b052ba49c3a44bd0bf769b7fa1
25. Lansiaux E, Azzouz R, Chazard E, Vromant A, Wiel E. "Artificial Intelligence Models for Predicting Triage in Emergency Departments." *JMIR Medical Informatics* 14:e83318, 2026. https://medinform.jmir.org/2026/1/e83318/PDF
26. Lal S, et al. "Predicting mortality in febrile adults: comparative performance of the MEWS, qSOFA, and UVA scores…" *EClinicalMedicine* 77:102856, 2024. https://doaj.org/article/472ab60c07af4c819f058bc83c88007e
27. GBC Ghana Online, "Why Ghana was right to say no: a cybersecurity expert's verdict on the $109 million US health deal", 14 May 2026. https://www.gbcghanaonline.com/general/why-ghana-was-right-to-say-no-a-cybersecurity-experts-verdict-on-the-109-million-us-health-deal/2026/
28. Meta AI, "Llama 3.2: Revolutionizing edge AI and vision with open, customizable models", 25 Sep 2024. https://ai.meta.com/blog/llama-3-2-connect-2024-vision-edge-mobile-devices/
29. Ghana News Agency, "Ghana to invest $250m in AI Centre, launch national strategy", 25 Apr 2026. https://gna.org.gh/2026/04/ghana-to-invest-250m-in-ai-centre-launch-national-strategy/
30. Hugging Face, meta-llama/Llama-3.2-3B-Instruct (Llama 3.2 Community License and Acceptable Use Policy). https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct
