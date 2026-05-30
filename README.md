# AI-Systematic-Review-Foundry
Ready-to-install GUI for human-in-the-loop AI assisted systematic review writing. Allows coordinating, managing, reviewing, and verifying review sourcing and information all from one easy to use app. 

# DISCLAIMER
This program can be used to write systematic reviews wicked fast. It is human-in-the-loop so you can either manually get your sources and write the review, or have AI help you with any step along the way. Verification of accurate information is YOUR responsibility however. There are a few automated tools to assist you in verifying if info pulled from sources is correct. Remember, you are the captain of this ship. Do not generate slop and proclaim it as gospel.

# Installation
You can install the files as a App on windows through the releases (clickable to the right of this readme): https://github.com/mclaughlinliam3/AI-Systematic-Review-Foundry/releases/latest

If you do not have windows, you can perhaps try just downloading the program files, install Python, installing the required dependencies, then find main_app.py and run this file with Python.

# Setting up APIs
To use automated obtainment of sources for the review, you need an NCBI API key. This is free to obtain and run and can pull sources from pubmed.

Get your **NCBI API Key** here: https://www.ncbi.nlm.nih.gov/datasets/docs/v2/api/api-keys/

To use the remote LLM API, currently Claude is the one that is supported. **Just create a Claude account and log in here to setup your API key**:
https://platform.claude.com/settings/keys
NOTE - For these sorts of APIs specifically, you will have to add funds because querying this model costs some money. Additionally, you may have to contend with rate limits if you use it a lot.

Lastly, it's possible to locally host your own LLM via Ollama. Ollama is a Python package that let's you install LLM models to your machine to be run on a GPU. Note that this will likely be substantially slower and with a simpler model than the remote APIs unless your GPU is a beast: https://pypi.org/project/ollama/

# General Note on AI review writing capabilities
In general, the AI's chances of misattributing sources go up if you feed it a huge amount of text at once. At very high levels, it may start to hallucinate. The framework of this program is designed to limit what text an AI can see at once so that it does this less. But if you do decide to feed it a bunch of text at once, do so at your own risk.

# Configuring Prompts and Context
- Prompts:
Go to prompt settings to edit your API keys and view/edit all default prompts this program uses. Whenever you send a prompt in the program, it will also show you what its about to say if you want to edit it then. Whenever an AI responds, you will also be shown the response to approve.

- Context:
Since the AI isn't good at reading a huge amount of text at once, you will want to mitigate how much is shown in any individual prompt that isn't iterative. Areas of this app that sends prompts have a 'Context' button that allows you to modullarly control what the corresponding prompt sends out. Context will open a simple window where you click what elements you want included. To assist you with this endeavor, this app has a few features where they AI can rate the relevance of sources to what element it's trying to write, allowing you to simply select the top-rated sources.

# Saving/Loading Sessions
By default, the system will save your sessions to your documents folder in an untitled.json file. It will Auto-Save to the active session every so often, but 'Ctrl + S' can also directly save the current session. Use 'File -> Save As' if you want to change the name and location of the file it's saving to. Use 'File -> Load' to load a different project and set that as the active session. Additionally, any custom parameters (ie prompts, API keys, etc) will be saved into a config.json file in your AppData folder somewhere.

# Review Writing Instructions
I may expand this tutorial down the line, but for now this is the gist:
1. Set a review topic in the 'Main Review' window.
2. Set up a set of boolean search terms to use in Pubmed under the 'Sources' tab. AI can optionally generate these for you. Set how many sources you want returned per search term.
3. Press 'Retrieve Sources' in the Sources tab to get all the sources from pubmed. These will organize themselves in the sources window for you and contain information such as their abtract, full text, and metadata.
4. Some sources may not retrieve an abstract or full text (ie wasn't free, or another reason. I am looking into whether institutional credentials can be used with remote API but right now some sources may not pull their text back). If this does happen, you can go to the source info, then under the doi you can find the website it came from, and then manually add missing info such as abstract/full text if that source is important to you. You can also manually add sources if you need to.
5. At the bottom of the 'Sources' tab, input your inclusion criteria if you have anything specific (ie sample size must be >10 or something). You can skip this step, but then the AI will use its own subjective decision making for source inclusion, which may be harder to predict.
6. Press 'Screen for Inclusion' to have the AI decide which studies belong in the Systematic Review. It will show in the source data its conclusion and why it thinks that.
7. ADDING TOPICS AND STATISTICS - The review itself can be written from just the source summaries. But for more control over what goes in, you can use the 'Topics' or 'Statistics' tabs for specific informational extraction. The 'Topics' tab is designed for specific research questions, ie 'What evidence is there that SSRIs improve Major Depressive Disorder?' and such. The 'Statistics' tab is more for pulling specific numerical data. The topics and stats tabs work about the same, so I am just going to describe topics here:
8. Generating topics/statistical questions - You can write your own topics, or you can press 'Auto-Generate Topics' to have the AI come up with some for your paper topic. Make sure to edit the prompt to let it know how many topics you need returned.
9. Pulling information for topics - Press 'AI Write Topic' to have the AI review the papers you send it. Check iterative mode to have it pull info one paper at a time (makes it more accurate with sourcing). If you have a smallish number of papers included in the context for the topic prompt, you can forego using the iterative feature which may save some time/API tokens, but the AI will just see everything at once and the response you get is what it is. To easily manage what sources go into a topic, press 'Rate Sources for Topics'. The AI will look at each source and decide its relevance to each topic. Then when you configure its context, you can just select the most relevant ones. If the response in a topic is very large, you can later press 'Distill' to have the AI try to trim down the associated text there. You can use 'Link to Sections' to configure a topic to automatically be included in that review sections context window (or you can just manually add it to the context in the main window).
10. Coming up with Results Subsections - The Review will ultimately be written in a piecemeal fashion, anchored around different subsections in the results. You can manually come up with these subsections, or you can have the AI come up with them by pressing 'Generate Results Topics' in the main window.
11. Rating Source Relevance for Results Subsections - Once you've created results subsections, go back to the 'Sources' tab. You can press 'Rate for Sections' to have the AI rate how relevant it thinks each source is for each results subsection. This can be used to easily control which source goes into which subsection to not overflow the AI with text.
12. Writing Review Sections - You can write each piece of the review by pressing the 'AI write' button next to it. By default, the Intro and each results subsection will see the top 10 rated sources for its respective section. By default, the discussion will just see the intro and full results. The conclusion and abstract will just be written referencing the rest of the paper. However, you can manually configure the context shown to each section by clicking its respective 'Context' button, in case you want it to see something specific. If you've created a lot of topics and want the paper anchored around those specific findings rather than individually sources, you'd need to configure that here and edit the prompt to not show other stuff you don't want. If you want, 'Write All Sections' at the top may be pressed to just have it write everything for you, assuming you've set up the above steps properly. Any review section can also be manually edited.
13. Verifying citations - The AI may sometimes get a citation wrong in its output. In the main window, for any citation (format [x]), you can right click this element. If the citation is correct, choosing 'Approve citation' will make it turn green, while choosing 'Disapprove citation' will make it turn red. If you are unsure, 'Auto-Detect' will a simple text matching algorithm to find the best match for the cited information from its proposed source and present it to you to review. Alternatively, 'AI-Detect' can ask the AI if it thinks that citation is right. If you feel it is wrong, 'Find Best Source Swap' will search through all your source summaries until it finds the best alternative match to what the current citation says. You will be shown both side-by-side and asked if you want the citation to be changed to the new one. Note that this is because the AI may write a piece of information that came verbatim from an actual source, but just cite it wrong. This is a much more frequent behavior than straight up hallucinating.
14. Exporting your review - After you are satisfied, 'File -> Export' can be used to convert your review into either a word doc, a pdf, or a .tex file (which you will need a Latex compiler to make look nice).
