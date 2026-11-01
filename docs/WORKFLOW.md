# Team workflow: branches, merging, timeline

**The deadline is Wed Nov 4, 9:00 PM ET. We submit by noon ET Nov 4.** US Daylight Saving Time ends Sun Nov 1, so from today **ET = UTC−5 and the UAE is 9 hours ahead of ET**.

---

## 1. Branches

| Branch | Owner | Builds | Doc |
|---|---|---|---|
| `main` | everyone (by team rule, PRs only; never push to it directly) | contracts, docs, merged work | this file |
| `platform-whatsapp` | **A** | WhatsApp bot, webhook, conversation state machine, approvals, store, report page, deployment | [workstream-A-platform.md](workstream-A-platform.md) |
| `verification-negotiation` | **B** | Muse Spark proof-take analysis, listing parser, VIN/vPIC, recalls, comps, scam scan, report builder, negotiation agent and policy | [workstream-B-intelligence.md](workstream-B-intelligence.md) |
| `eval-demo` | **C** | 100-listing study, red team, light check, negotiation study, demo script and video, submission | [workstream-C-eval-demo.md](workstream-C-eval-demo.md) |

Pick roles tonight. Suggested split:
- **B:** the strongest Python/prompting person. B's code is the brain, and B runs the day-1 test.
- **A:** whoever has done webhooks or APIs.
- **C:** the person best at people, video and storytelling. C also has the most live testing to coordinate.

## 2. First-time setup (each person)

```bash
git clone https://github.com/Keshav-kh/tirekick.git
cd tirekick
git checkout <your-branch>            # platform-whatsapp | verification-negotiation | eval-demo
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                  # ask in the group for the shared keys; never commit .env
pytest                                # must be green before you start
```

## 3. Daily loop

```bash
# start of each session: pull everyone else's merged work into your branch
git checkout <your-branch>
git fetch origin
git merge origin/main                 # conflicts should be rare; see §6

# work, commit small and often
git add <your files>
git commit -m "verify: bulb-check structured output + majority vote"
git push origin <your-branch>
```

**Rules**
1. Edit only the folders you own (see [CONTRACTS.md §1](CONTRACTS.md#1-folder-ownership-who-may-edit-what)).
2. **Never commit `.env`, keys, or `data/`.** Both are in `.gitignore`; don't force-add them.
3. Run `pytest` before every push. CI runs it on every PR too.
4. Commit messages start with your area: `platform:`, `verify:`, `negotiate:`, `eval:`, `demo:`, `docs:`, `contracts:`.
5. Hero demo clips and other big media go in **Google Drive**, not git. Link to them from `demo/ASSETS.md`.

## 4. Merging into `main` (pull requests)

```bash
gh pr create --base main --head <your-branch> --title "verify: proof-take analysis v1" --body "What / how tested / screenshots"
```

- **One teammate reviews** every PR. Quick reviews are fine, but someone other than the author has to look.
- **CI must be green** (`.github/workflows/tests.yml` runs `pytest`).
- Use **"Squash and merge"** so `main` stays readable.
- Don't delete your branch after merging. Keep working on it and merge `main` back in.

**Contract changes** (`tirekick/models.py`, `docs/CONTRACTS.md`): open a separate small PR from a short-lived branch (`contracts/<what>`). Post it in the group, get a 👍 from both others, then merge. Everyone then runs `git merge origin/main`.

## 5. Merge order and integration checkpoints

Merge in **dependency order** at each checkpoint: B first (A and C call B's functions), then A, then C.

| Checkpoint | When (ET) | When (UAE) | Definition of done |
|---|---|---|---|
| **Kickoff** | Sun Nov 1, 9 PM | Mon 6 AM | Roles picked; everyone has `pytest` green on their branch; B's day-1 test result posted (GO or fallback) |
| **Integration 1** | Mon Nov 2, 9 PM | Tue 6 AM | B: `analyze_proof_take`, `decode_vin`, `lookup_recalls`, `build_report` real and merged. A: full chat flow working on `/dev/simulate` with real B code. C: 50+ listings collected, red-team and light-check clips filmed. **One honest and one shady clip go end to end on a real phone.** |
| **Feature freeze** | Tue Nov 3, 9 PM | Wed 6 AM | Negotiation, comps, scam scan merged; deployed on a stable URL; all four studies run; numbers in `eval/RESULTS.md`; demo takes recorded. **After this, only bug fixes.** |
| **Submit** | Wed Nov 4, noon | Wed 9 PM | Video uploaded, repo README final, submission form done. 9 hours of buffer before the 9 PM ET deadline. |

Integration ritual (about 30 minutes, everyone on a call):
1. B merges their PR and the others pull: `git fetch && git merge origin/main`.
2. A merges, then everyone pulls again.
3. C merges.
4. Each person runs `pytest` and the end-to-end smoke test: `TIREKICK_DEV=1 uvicorn tirekick.app:app` plus the `/dev/simulate` script in `demo/smoke_test.md`.
5. Write down what broke; the owner fixes it on their branch.

## 6. If you hit a merge conflict

Folder ownership should prevent most conflicts. If one happens:
```bash
git merge origin/main          # shows the conflicting files
# open each one, keep both sides' intent, remove the <<<< ==== >>>> markers
pytest
git add <files> && git commit  # completes the merge
```
If the conflict is in someone else's file, **stop and ask them**. Don't guess.

## 7. Hour-by-hour plan

### Sun Nov 1 (today)
- **All (30 min):** roles, clone, setup, `.env` keys shared privately (not in git or the group chat).
- **B:** the **day-1 test** ([workstream B §0](workstream-B-intelligence.md#0-day-1-test-do-this-first)). Post the GO or NO-GO result by 9 PM ET.
- **A:** create the Meta app and WhatsApp test number, then get the webhook echo working through ngrok.
- **C:** film 5–8 cold-start clips on friends' cars (2 with tape over the check-engine light) for B's test, and start the listing spreadsheet.

### Mon Nov 2
- **B:** the real `analyze_proof_take` (3-run vote), `decode_vin`, `lookup_recalls`, and `build_report` with frame extraction.
- **A:** the orchestrator state machine, approvals (1/2/3), store, report page v1; everything working with fakes first.
- **C:** 50+ listings, red-team clips (6 fake types), the negotiation-study sign-ups (10 friends).
- **9 PM ET: Integration 1.**

### Tue Nov 3
- **B:** `draft_offer` plus policy, `apply_seller_reply`, `price_comps`, `scan_chat`.
- **A:** deploy to a stable host, polish the WhatsApp copy and the report page, set up SAM highlight display.
- **C:** run the red team, light check and negotiation study; finish the 100 listings; write `eval/RESULTS.md`; record demo takes.
- **9 PM ET: feature freeze.**

### Wed Nov 4
- **7–10 AM ET:** final demo recording (cached hero clips), video edit, README with the numbers.
- **10–11:30 AM ET:** submission write-up and form, plus a final check that the repo is public, if the rules require it.
- **Noon ET: submit.**

## 8. Communication

- Standups at **9 AM ET (6 PM UAE)** and **9 PM ET (6 AM UAE)**, 10 minutes each: what's done, what's next, what's blocked.
- Blockers go in the group chat right away, tagged with the owner's area (`[verify]`, `[platform]`, `[eval]`).
- Use GitHub Issues for bugs in someone else's area, with steps to reproduce and the clip or deal ID.
