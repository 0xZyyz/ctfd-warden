"""Client telemetry labels. Headers and browser signals are hints, not proof of AI use."""

import re

from flask import request

# Self-identifying AI agents and fetchers (substring of the User-Agent, case-insensitive) -> label.
AI_AGENTS = [
    # OpenAI
    ("chatgpt-user", "ChatGPT agent"),
    ("oai-searchbot", "OpenAI SearchBot"),
    ("gptbot", "GPTBot"),
    ("openai", "OpenAI"),
    ("codex", "OpenAI Codex"),
    # Anthropic
    ("claude-user", "Claude"),
    ("claude-searchbot", "Claude"),
    ("claudebot", "ClaudeBot"),
    ("claude-web", "Claude"),
    ("anthropic", "Anthropic"),
    # Google
    ("googleagent", "Google agent (Mariner)"),
    ("gemini", "Gemini"),
    ("google-extended", "Gemini"),
    ("google-cloudvertexbot", "Google Vertex AI"),
    ("googleother", "Google fetcher"),
    # Perplexity / Meta / Mistral / Apple / Amazon / Microsoft
    ("perplexity", "Perplexity"),
    ("comet", "Perplexity Comet"),
    ("meta-external", "Meta AI"),
    ("facebookbot", "Meta AI"),
    ("mistral", "Mistral"),
    ("applebot-extended", "Apple Intelligence"),
    ("amazonbot", "Amazon"),
    ("novaact", "Amazon Nova Act"),
    ("nova-act", "Amazon Nova Act"),
    ("copilot", "Microsoft Copilot"),
    ("bingpreview", "Bing/Copilot"),
    # Chinese labs
    ("bytespider", "ByteDance"),
    ("tiktokspider", "ByteDance"),
    ("doubao", "Doubao"),
    ("deepseek", "DeepSeek"),
    ("qwen", "Qwen"),
    ("kimi", "Kimi"),
    ("moonshot", "Kimi"),
    ("chatglm", "ChatGLM"),
    ("zhipu", "ChatGLM"),
    ("pangubot", "Huawei PanGu"),
    ("baiduspider-render", "Baidu AI"),
    ("yisouspider", "Yisou"),
    # other assistants, agents and AI crawlers
    ("cohere", "Cohere"),
    ("duckassist", "DuckAssist"),
    ("youbot", "You.com"),
    ("diffbot", "Diffbot"),
    ("ai2bot", "AI2"),
    ("ccbot", "Common Crawl"),
    ("timpibot", "Timpi"),
    ("omgili", "Omgili"),
    ("imagesift", "ImageSift"),
    ("kangaroo bot", "Kangaroo"),
    ("grok", "xAI Grok"),
    ("xai-", "xAI"),
    ("manus", "Manus"),
    ("devin", "Devin"),
    ("browser-use", "browser-use"),
    ("genspark", "Genspark"),
    ("agentql", "AgentQL"),
    ("skyvern", "Skyvern"),
    ("stagehand", "Stagehand"),
    ("multion", "MultiOn"),
    ("lavague", "LaVague"),
    ("openclaw", "OpenClaw"),
    ("opencode", "opencode"),
    ("aider", "Aider"),
    ("cline", "Cline"),
    ("cursor", "Cursor"),
    ("windsurf", "Windsurf"),
    ("hyperbrowser", "Hyperbrowser"),
    ("browserbase", "Browserbase"),
    ("steel-browser", "Steel"),
    ("firecrawl", "Firecrawl"),
    ("jina", "Jina Reader"),
    ("exa-", "Exa"),
    ("tavily", "Tavily"),
    ("serper", "Serper"),
    ("apify", "Apify"),
    ("scrapegraph", "ScrapeGraphAI"),
    ("langchain", "LangChain"),
    ("llamaindex", "LlamaIndex"),
    ("crewai", "CrewAI"),
    ("autogpt", "AutoGPT"),
    ("agentgpt", "AgentGPT"),
    ("babyagi", "BabyAGI"),
    ("ai-agent", "self-declared AI agent"),
    ("ai agent", "self-declared AI agent"),
]
# Scripting / headless clients -> label. Normal in a CTF; logged as context, not as proof.
AUTOMATION = [
    # browsers under automation
    ("webdriverio", "WebdriverIO"),
    ("nightwatch", "Nightwatch"),
    ("testcafe", "TestCafe"),
    ("katalon", "Katalon"),
    ("geckodriver", "GeckoDriver"),
    ("marionette", "Marionette"),
    ("browserless", "Browserless"),
    ("chrome-lighthouse", "Lighthouse"),
    ("cefsharp", "CefSharp"),
    ("qtwebengine", "QtWebEngine"),
    ("browserstack", "BrowserStack"),
    ("lambdatest", "LambdaTest"),
    ("saucelabs", "Sauce Labs"),
    ("crawlee", "Crawlee"),
    ("chromedp", "chromedp"),
    ("pyppeteer", "pyppeteer"),
    ("undetected", "undetected-chromedriver"),
    ("nodriver", "nodriver"),
    ("drissionpage", "DrissionPage"),
    ("botasaurus", "Botasaurus"),
    ("headlesschrome", "Headless Chrome"),
    ("headless", "headless browser"),
    ("playwright", "Playwright"),
    ("puppeteer", "Puppeteer"),
    ("selenium", "Selenium"),
    ("webdriver", "WebDriver"),
    ("chromedriver", "ChromeDriver"),
    ("phantomjs", "PhantomJS"),
    ("electron", "Electron"),
    ("cypress", "Cypress"),
    ("nightmare", "Nightmare"),
    ("zombie", "Zombie.js"),
    ("jsdom", "jsdom"),
    ("htmlunit", "HtmlUnit"),
    # Python
    ("python-requests", "python-requests"),
    ("python-httpx", "httpx"),
    ("aiohttp", "aiohttp"),
    ("python-urllib", "urllib"),
    ("python/", "Python"),
    ("httpcore", "httpcore"),
    ("pycurl", "pycurl"),
    ("mechanize", "Mechanize"),
    ("scrapy", "Scrapy"),
    ("locust", "Locust"),
    # JS / TS runtimes and libs
    ("node-fetch", "node-fetch"),
    ("undici", "Node undici"),
    ("node/", "Node"),
    ("axios", "axios"),
    ("got (", "got"),
    ("superagent", "superagent"),
    ("needle/", "needle"),
    ("deno/", "Deno"),
    ("bun/", "Bun"),
    # other languages
    ("go-http-client", "Go"),
    ("reqwest", "Rust reqwest"),
    ("hyper/", "Rust hyper"),
    ("ureq", "Rust ureq"),
    ("java/", "Java"),
    ("apache-httpclient", "Apache HttpClient"),
    ("apachebench", "ApacheBench"),
    ("okhttp", "okhttp"),
    ("jersey", "Jersey"),
    ("unirest", "Unirest"),
    ("libwww-perl", "Perl"),
    ("lwp-", "Perl LWP"),
    ("ruby", "Ruby"),
    ("faraday", "Ruby Faraday"),
    ("typhoeus", "Ruby Typhoeus"),
    ("guzzle", "PHP Guzzle"),
    ("symfony", "PHP Symfony"),
    ("php/", "PHP"),
    ("dart/", "Dart"),
    ("dart:io", "Dart"),
    ("restsharp", "C# RestSharp"),
    ("powershell", "PowerShell"),
    ("winhttp", "WinHTTP"),
    ("lua-resty", "Lua"),
    ("elixir", "Elixir"),
    ("httpoison", "Elixir"),
    ("hackney", "Elixir"),
    ("alamofire", "Swift Alamofire"),
    # command-line and API tools
    ("curl/", "curl"),
    ("libcurl", "libcurl"),
    ("wget/", "wget"),
    ("httpie", "HTTPie"),
    ("hurl", "Hurl"),
    ("postmanruntime", "Postman"),
    ("insomnia", "Insomnia"),
    ("paw/", "Paw"),
    ("bruno", "Bruno"),
    ("thunder client", "Thunder Client"),
    ("jmeter", "JMeter"),
    ("siege", "Siege"),
    ("wrk", "wrk"),
    ("vegeta", "Vegeta"),
    # security tooling
    ("sqlmap", "sqlmap"),
    ("nikto", "Nikto"),
    ("nuclei", "nuclei"),
    ("ffuf", "ffuf"),
    ("gobuster", "gobuster"),
    ("dirbuster", "DirBuster"),
    ("dirb", "dirb"),
    ("dirsearch", "dirsearch"),
    ("feroxbuster", "feroxbuster"),
    ("wfuzz", "wfuzz"),
    ("wpscan", "WPScan"),
    ("nmap", "Nmap"),
    ("masscan", "masscan"),
    ("zgrab", "zgrab"),
    ("owasp zap", "OWASP ZAP"),
    ("zaproxy", "OWASP ZAP"),
    ("burp", "Burp Suite"),
    ("arachni", "Arachni"),
    ("skipfish", "skipfish"),
    ("w3af", "w3af"),
    ("whatweb", "WhatWeb"),
    ("wappalyzer", "Wappalyzer"),
    ("httpx -", "httpx (projectdiscovery)"),
    ("katana", "katana"),
    ("hakrawler", "hakrawler"),
    ("subfinder", "subfinder"),
    ("metasploit", "Metasploit"),
    ("commix", "commix"),
    ("xsstrike", "XSStrike"),
    ("dalfox", "dalfox"),
    ("patator", "patator"),
    # generic
    ("agent", "self-declared agent"),
    ("bot", "bot"),
    ("crawler", "crawler"),
    ("spider", "spider"),
    ("scraper", "scraper"),
    ("fetch", "fetcher"),
]
BROWSER_MARKERS = ("mozilla/", "chrome/", "safari/", "firefox/", "edg/", "opr/")


def _ua_has(ua, needle):
    """Substring match, but short needles (<= 5 chars) must start at a token boundary, so that e.g.
    "bot" does not match "Botim" and "ab/" does not match "FB_IAB/" in real phone User-Agents."""
    if len(needle) > 5:
        return needle in ua
    suffix = r"(?![a-z0-9])" if needle[-1].isalnum() else ""
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + suffix, ua) is not None


def _client_label():
    """(kind, label) from headers alone: 'ai' | 'automation', or None for a normal browser."""
    h = request.headers
    if h.get("Signature-Agent") or h.get("Signature-Input"):
        return "automation", "agent signature header (unverified)"
    ua = (h.get("User-Agent") or "").lower()
    if not ua:
        return "automation", "no User-Agent"
    for needle, label in AI_AGENTS:
        if _ua_has(ua, needle):
            return "ai", label
    # Headless Chromium (Playwright/Puppeteer) announces itself in the client hints even when the
    # User-Agent was rewritten to look like a normal browser.
    if "headless" in (h.get("Sec-CH-UA") or "").lower():
        return "automation", "Headless Chrome (client hints)"
    for needle, label in AUTOMATION:
        if _ua_has(ua, needle):
            return "automation", label
    # A browser-looking User-Agent that sends no Accept-Language: real browsers always do, driver-less
    # automation (Playwright request contexts, httpx with a copied UA, ...) usually does not.
    if any(m in ua for m in BROWSER_MARKERS) and not h.get("Accept-Language"):
        return "automation", "browser UA without Accept-Language"
    return None


def classify_client():
    """('api-token' | 'ai' | 'automation', label), or None for a normal browser session.

    A request authenticated with a CTFd access token (Authorization: Token ...) is flagged whatever its
    User-Agent says: that is how scripts and AI agents drive the API without a browser."""
    found = _client_label()
    auth = (request.headers.get("Authorization") or "").lower()
    if auth.startswith("token "):
        return "api-token", "API token" + (f" · {found[1]}" if found else "")
    return found
