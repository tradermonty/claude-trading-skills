# API Key Detection and Setup Flow

Step 3 detail, moved verbatim from `SKILL.md`.

#### 3.1 Check Environment Variable (CLI/Desktop)

```bash
if [ ! -z "$FMP_API_KEY" ]; then
  echo "✓ API key found in environment"
  API_KEY=$FMP_API_KEY
fi
```

If environment variable is set, proceed to Step 4.

#### 3.2 Prompt User for API Key (Desktop/Web)

If environment variable not found, use AskUserQuestion tool:

**Question Configuration**:
```
Question: "This skill requires an FMP API key to retrieve earnings data. Do you have an FMP API key?"
Header: "API Key"
Options:
  1. "Yes, I'll provide it now" → Proceed to 3.3
  2. "No, get free key" → Show instructions (3.2.1)
  3. "Skip API, use manual entry" → Jump to Step 8 (fallback mode)
```

**3.2.1 If user chooses "No, get free key"**:

Provide instructions:
```
To get a free FMP API key:

1. Visit: https://site.financialmodelingprep.com/developer/docs
2. Click "Get Free API Key" or "Sign Up"
3. Create account (email + password)
4. Receive API key immediately
5. Free tier includes 250 API calls/day (sufficient for daily use)

Once you have your API key, please select "Yes, I'll provide it now" to continue.
```

#### 3.3 Request API Key Input

If user has API key, request input:

**Prompt**:
```
Please paste your FMP API key below:

(Your API key will only be stored for this conversation session and will be forgotten when the session ends. For regular use, consider setting the FMP_API_KEY environment variable.)
```

**Store API key in session variable**:
```
API_KEY = [user_input]
```

**Confirm with user**:
```
✓ API key received and stored for this session.

Security Note:
- API key is stored only in current conversation context
- Not saved to disk or persistent storage
- Will be forgotten when session ends
- Do not share this conversation if it contains your API key

Proceeding with earnings data retrieval...
```
