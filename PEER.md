# Peer Review

How your README is written, reviewed, improved and submitted. Everything happens on the GitHub website, in your browser. You do not need to install anything, use a terminal, or download the repository.

**Why only the website?** Every step of this assignment can be done and explained inside GitHub, so everyone works the same way and every step below matches what you see. Do not clone the repository or work in another editor. Course staff can only help with problems that happen on the GitHub website.

## The people

- **Author:** you, writing the README for your repository.
- **Reviewers:** two classmates, who review your README. You will also be a reviewer for two other classmates. Your instructor will tell you who your reviewers are.
- **Instructor and course staff:** they can see your repository and your review. Your instructor will give you their GitHub usernames.

## A few words you will see

- **Repository:** your copy of the project on GitHub: all its files and their history.
- **Commit:** a saved change. Every time you click **Commit changes**, GitHub saves a new version and keeps the old ones.
- **Branch:** a separate draft copy of your files, inside the same repository. Your repository starts with one branch, called `main`: think of it as the finished, published version. You will write your README on a second branch, called `readme-draft`. Nothing you do on `readme-draft` changes `main` until you choose to bring it across.
- **Pull request:** a request to bring the changes on your draft branch into `main`. It is also the place where reviewers read your changes and comment on them, line by line. The pull request is the review.
- **Merge:** bringing the draft into `main`, once your reviewers approve. After merging, your README is part of `main`.

## The phases

| Phase | Who | What happens | Done when |
|---|---|---|---|
| 0. Set up | Author | Add your reviewers, instructor and course staff to your repository | Everyone has accepted the invitation |
| 1. Draft | Author | Write `README.md` on a new branch and open a pull request | The pull request is open and your two reviewers are requested |
| 2. Review | Reviewers | Comment on the README, line by line, and submit a review | Both reviewers have submitted a review |
| 3. Revise | Author | Make changes, answer every comment, and ask for another review | Every comment has an answer and you have re-requested review |
| 4. Approve | Reviewers | Check the changes and approve | Both reviewers have approved |
| 5. Merge | Author | Merge the pull request into `main` | The README is on `main` |
| 6. Submit | Author | Convert `README.md` to a PDF and submit it on Canvas | The PDF is on Canvas |

There is always at least one round of feedback and revision: phase 2, then phase 3, then phase 4. If a reviewer asks for more changes in phase 4, go back to phase 3. You may not merge until **both** reviewers have approved.

---

## Phase 0: Set up

### Add your reviewers, instructor and course staff

Your repository is private, so only the people you add can see it.

1. Go to your repository on GitHub.
2. Click **Settings** (the tab with the gear icon, at the top of the repository).
3. In the left sidebar, under **Access**, click **Collaborators**. GitHub may ask for your password.
4. Click **Add people**.
5. Type the person's GitHub username, choose them from the list, and click **Add to this repository**.
6. Repeat for each person: your two reviewers, your instructor, and each member of course staff.

Each person gets an invitation by email and on GitHub. They cannot see your repository until they accept it.

### Accept invitations you receive

When a classmate adds you as a reviewer, you get an email from GitHub. Open it and click **View invitation**, then **Accept invitation**. You can also find invitations under the bell icon (top right of any GitHub page).

---

## Phase 1: Draft (author)

### Create README.md on a new branch

Do this once, to start the README.

1. Go to the front page of your repository (the **Code** tab). Check that the branch button near the top left says `main`.
2. Click **Add file**, then **Create new file**.
3. In the name box, type exactly `README.md`. It goes at the top level, next to `START.md`.
4. Write in the editor. Click the **Preview** tab at any time to see how it will look. Follow [SPEC.md](SPEC.md) for what goes in it.
5. Click the green **Commit changes...** button (top right).
6. In the box that opens:
   - Leave the commit message as it is, or write a short one such as "First draft of README".
   - **Choose "Create a new branch for this commit and start a pull request."** This is the important step: do not choose "Commit directly to the `main` branch".
   - In the branch name box, type `readme-draft`.
7. Click **Propose changes**.

GitHub now shows the **Open a pull request** page. Continue below.

### Open the pull request

1. **Title:** something clear, such as "README for tempo".
2. **Description:** write it yourself, in a few sentences: what this README covers, anything you are unsure of, and what you would most like your reviewers to look at. See [Write the description yourself](#write-the-description-yourself) below.
3. On the right, click **Reviewers** (or the gear next to it) and choose your two reviewers. Only people who have accepted your invitation appear.
4. Click **Create pull request**.

Your pull request now has its own page, with tabs for **Conversation**, **Commits** and **Files changed**. Your reviewers get a notification.

### Keep working on the draft

You can keep editing until your reviewers start, and you will edit again in phase 3. Always edit on the `readme-draft` branch:

1. Open your pull request: click the **Pull requests** tab of your repository, then your pull request.
2. Click the **Files changed** tab.
3. On the `README.md` box, click the **...** button (top right of the box), then **Edit file**.
4. Make your changes, then click **Commit changes...**.
5. Check that the box says **Commit directly to the `readme-draft` branch**, then click **Commit changes**.

The pull request updates on its own. You never need to open a second pull request.

### Write the description yourself

GitHub may offer to write the pull request description for you with Copilot, its AI assistant, through a Copilot button or suggested text that appears as you type in the description box. **Do not use it.**

The description is your message to your reviewers: it tells them what you did and where to look. They take it on trust, so it has to say what you actually did, in your words. An AI summary of your changes can sound right while describing them wrongly, and your reviewers would then look in the wrong place.

- If suggested text appears as you type, you can switch it off: click the Copilot icon above the description box and choose **Disabled** under **Autocomplete**.
- If Copilot text ends up in your description anyway, read it against what you actually did, rewrite anything that is wrong or vague, and add a line at the end saying "Part of this description was written by Copilot and checked by me."

### If you committed to main by mistake

If `README.md` went onto `main` instead of a new branch, there is nothing for your reviewers to review. Fix it like this:

1. Open `README.md` on `main`, select all the text in it, and copy it somewhere safe.
2. Click the **...** button (top right of the file), then **Delete file**, and commit directly to `main`.
3. Start again at [Create README.md on a new branch](#create-readmemd-on-a-new-branch) and paste your text back in.

---

## Phase 2: Review (reviewers)

You are reviewing a classmate's README. Use [SPEC.md](SPEC.md): each section has a **Reviewers check** line. Then do what a real reader would do: try to follow the Install and Usage instructions against the project's own files in that repository, and note the first place you get stuck.

### Open the pull request

1. Open the email or notification about the review request, or go to the author's repository and click the **Pull requests** tab, then their pull request.
2. Read the **Description** on the **Conversation** tab first.
3. Click the **Files changed** tab. Because `README.md` is a new file, every line is shown in green, and every line can be commented on.

To see the README as it will look on GitHub, click the **...** button on the file, then **View file**. To comment, come back to **Files changed**.

### Comment on a line

1. Hover over a line in **Files changed**. A blue **+** button appears next to it. Click it.
   - To comment on several lines at once, click the **+** on the first line and drag down to the last.
2. Write your comment. Be specific: say what is wrong or unclear, and why it matters to a reader.
3. To propose exact new wording, click the **Add a suggestion** button in the comment toolbar (an icon of a page with a plus and minus). GitHub fills in the current line; edit it into what you think it should say. The author can then accept it with one click.
4. Click **Start a review** for your first comment, then **Add review comment** for the rest. Your comments stay private until you submit the review.

### Submit your review

1. When you have finished, click **Submit review** (in some versions of GitHub it is labelled **Review changes**), at the top right of **Files changed**.
2. Write a short overall summary: what works, and the two or three changes that matter most.
3. Choose one:
   - **Comment:** general feedback, no decision yet.
   - **Request changes:** the README needs changes before it can be merged. In the first round this is the usual choice.
   - **Approve:** do not choose this in the first round. Every README gets at least one round of revision.
4. Click **Submit review**.

---

## Phase 3: Revise (author)

1. Open your pull request. On the **Conversation** tab, read every review and comment.
2. **For a suggestion:** if you agree, click **Commit suggestion** under it, then **Commit changes**. To accept several at once, click **Add suggestion to batch** on each, then **Commit suggestions**.
3. **For other comments:** edit `README.md` on the `readme-draft` branch, as in [Keep working on the draft](#keep-working-on-the-draft).
4. **Answer every comment.** Reply under it, saying what you changed, or why you decided not to change it. Then click **Resolve conversation**. Disagreeing is allowed; ignoring a comment is not.
5. When you have dealt with everything, ask your reviewers to look again: on the right of the **Conversation** tab, under **Reviewers**, click the circular-arrows icon next to each reviewer's name (**Re-request review**).
6. Optionally, add a comment at the bottom of the **Conversation** tab summarizing what changed in this round.

---

## Phase 4: Approve (reviewers)

1. Open the pull request again. Read the author's replies on the **Conversation** tab.
2. Click **Files changed**. GitHub may offer to show only what changed since your last review; use it to check the new edits.
3. Click **Submit review** (or **Review changes**) and choose:
   - **Approve**, if the README now meets [SPEC.md](SPEC.md) and you could follow its instructions. Add a sentence on what convinced you.
   - **Request changes**, if something important is still missing or wrong. Say exactly what. The author goes back to phase 3.
4. Click **Submit review**.

---

## Phase 5: Merge (author)

Only when **both** reviewers have approved. The **Conversation** tab shows a green tick and "approved" next to each reviewer's name.

1. Scroll to the bottom of the **Conversation** tab.
2. Click **Merge pull request**, then **Confirm merge**.
3. GitHub offers **Delete branch**. You can click it: the branch is no longer needed, and its history is kept in the pull request.

Your README is now on `main`. Go to the **Code** tab of your repository: GitHub shows it on the front page.

GitHub does not stop you from merging early, so check the approvals yourself before you click.

---

## Phase 6: Submit (author)

You submit your README as a PDF on Canvas.

1. In your repository, on the **Code** tab, check the branch button says `main`, then click `README.md`.
2. Click the **Download raw file** button (a downward arrow, top right of the file). Your browser saves `README.md`.
3. Go to https://cloudconvert.com/md-to-pdf.
4. Click **Select File**, choose **From my Computer**, and pick the `README.md` you downloaded.
5. Click **Convert**. When it finishes, click **Download**.
6. Open the PDF and check it: every section should be there and readable. Images stored in your repository, such as a banner, may not appear in the PDF.
7. Upload the PDF to the assignment on Canvas.
