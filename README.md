# Retirement Daily Digest

A tool that curates daily headlines and news relevant to a 60+ audience, covering:
- Personal finance & investing
- Social Security & Medicare
- Job security & retirement planning
- Health & fitness for seniors
- Inter-generational relationships
- Legislation & government action

## Output
- HTML email digest with summaries and source links
- Overall daily summary
- YouTube content ideas based on the day's news

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and add your API keys:
   ```bash
   cp .env.example .env
   ```

3. Run the digest:
   ```bash
   python digest.py
   ```

4. Optional: set up a daily cron job:
   ```bash
   # Run at 7am every day
   0 7 * * * cd /path/to/retirement-digest && python digest.py
   ```

## Configuration

Edit `config.py` to customize:
- Topics and search queries
- Email settings (SMTP)
- Number of articles per topic
- Output format
