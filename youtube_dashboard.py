#!/usr/bin/env python3
"""
YouTube Trends Dashboard Generator — static HTML with two tabs:
1. Trending: top 100 videos with topic/angle/content_type tags and filters
2. Competitors: recent videos from tracked channels
"""

import argparse
import json
import logging
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE importing config (which reads env vars at import time)
load_dotenv(Path(__file__).parent / ".env")

from youtube import gather_youtube_trends, gather_competitor_videos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dashboard")


def format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def generate_dashboard(
    yt_data: dict, competitor_videos: list, date_display: str
) -> str:
    videos = yt_data.get("videos", [])
    trend_summary = yt_data.get("trend_summary", "")

    trend_paragraphs = [p.strip() for p in trend_summary.split("\n\n") if p.strip()]
    trend_html = "\n".join(f"<p>{p}</p>" for p in trend_paragraphs)

    # Collect filter options from tagged data
    topics = sorted(set(v.get("topic", "Other") for v in videos))
    angles = sorted(set(v.get("angle", "Other") for v in videos))
    content_types = sorted(set(v.get("content_type", "Other") for v in videos))
    languages = sorted(set(v.get("language", "unknown") for v in videos))
    all_jtbd = [
        "Emotional Stabilization",
        "Explain Concept",
        "Social Calibration",
        "Decision Outsourcing",
        "Identity & Community",
        "Incite Fear",
        "Other",
    ]

    def make_options(items):
        return "\n".join(f'<option value="{x}">{x}</option>' for x in items)

    # Competitor channel names
    comp_channels = sorted(set(v["channel"] for v in competitor_videos))

    videos_json = json.dumps(videos, default=str)
    comp_json = json.dumps(competitor_videos, default=str)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Retirement Content Trends — {date_display}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8f9fa; color: #1a1a2e; line-height: 1.6; }}
        .header {{ background: linear-gradient(135deg, #1a5276, #2e86c1); padding: 32px; color: #fff; }}
        .header h1 {{ font-size: 22px; font-weight: 600; margin: 0 0 4px 0; }}
        .header .sub {{ font-size: 13px; color: #d6e9f5; }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 20px 24px; }}

        /* Tabs */
        .tabs {{ display: flex; gap: 0; margin-bottom: 20px; border-bottom: 2px solid #e1e4e8; }}
        .tab {{ padding: 10px 24px; font-size: 14px; font-weight: 600; color: #666; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; }}
        .tab:hover {{ color: #333; }}
        .tab.active {{ color: #1a5276; border-bottom-color: #1a5276; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}

        /* Cards */
        .card {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 20px; margin-bottom: 16px; }}
        .card h2 {{ font-size: 15px; font-weight: 600; color: #c0392b; margin-bottom: 10px; }}
        .card p {{ font-size: 14px; color: #444; margin-bottom: 8px; }}

        /* Filters */
        .filters {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 14px 18px; margin-bottom: 14px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
        .filters label {{ font-size: 13px; color: #555; }}
        .filters select {{ padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }}
        .filter-count {{ font-size: 13px; color: #999; margin-left: auto; }}

        /* Tags */
        .tag {{ display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 3px; font-weight: 600; margin-right: 4px; }}
        .tag-topic {{ background: #e8f4fd; color: #1a5276; }}
        .tag-angle {{ background: #fef3e2; color: #b45309; }}
        .tag-type {{ background: #e8f5e9; color: #2e7d32; }}
        .tag-short {{ background: #fff3cd; color: #856404; }}
        .tag-long {{ background: #d4edda; color: #155724; }}
        .tag-live {{ background: #f3e5f5; color: #7b1fa2; }}
        .tag-lang {{ background: #e8eaf6; color: #3949ab; }}
        .tag-jtbd {{ background: #fce4ec; color: #c62828; }}

        /* Video row */
        .vrow {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 14px 18px; margin-bottom: 8px; display: flex; gap: 12px; align-items: flex-start; }}
        .vrow:hover {{ border-color: #2e86c1; }}
        .vrank {{ font-size: 13px; font-weight: 700; color: #bbb; min-width: 28px; padding-top: 2px; }}
        .vcontent {{ flex: 1; }}
        .vcontent a {{ font-size: 14px; font-weight: 600; color: #1a5276; text-decoration: none; }}
        .vcontent a:hover {{ text-decoration: underline; }}
        .vmeta {{ font-size: 12px; color: #888; margin-top: 3px; }}
        .vmeta .ch {{ color: #555; font-weight: 500; }}
        .vsummary {{ font-size: 13px; color: #555; margin-top: 5px; }}
        .vwhy {{ font-size: 12px; color: #999; font-style: italic; margin-top: 3px; }}
        .vstats {{ display: flex; gap: 14px; min-width: 170px; justify-content: flex-end; flex-shrink: 0; }}
        .vstats .s {{ text-align: center; }}
        .vstats .sv {{ font-size: 15px; font-weight: 700; color: #333; display: block; }}
        .vstats .sl {{ font-size: 10px; color: #999; text-transform: uppercase; }}

        .footer {{ padding: 28px 0; text-align: center; font-size: 12px; color: #999; border-top: 1px solid #e1e4e8; margin-top: 24px; }}

        @media (max-width: 768px) {{
            .vrow {{ flex-direction: column; }}
            .vstats {{ justify-content: flex-start; min-width: auto; }}
            .filters {{ flex-direction: column; align-items: flex-start; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div style="max-width: 1100px; margin: 0 auto;">
            <h1>📺 Retirement Content Trends</h1>
            <div class="sub">What's getting traction · {date_display}</div>
        </div>
    </div>

    <div class="container">
        <!-- Tabs -->
        <div class="tabs">
            <div class="tab active" onclick="switchTab('trending')">Trending Videos</div>
            <div class="tab" onclick="switchTab('competitors')">Competitor Watch</div>
        </div>

        <!-- TAB 1: Trending -->
        <div id="tab-trending" class="tab-content active">
            <div class="card">
                <h2>🔥 What's Working Right Now</h2>
                {trend_html if trend_html else '<p>No trend analysis available.</p>'}
            </div>

            <div class="filters">
                <span style="font-size: 13px; font-weight: 600; color: #333;">Filter:</span>
                <label>Topic <select id="f-topic" onchange="applyFilters()"><option value="all">All</option>{make_options(topics)}</select></label>
                <label>Format <select id="f-format" onchange="applyFilters()"><option value="all">All</option><option value="Long">Long-form</option><option value="Short">Shorts</option><option value="Livestream">Livestream</option></select></label>
                <label>Language <select id="f-lang" onchange="applyFilters()"><option value="en" selected>English</option><option value="all">Global</option></select></label>
                <span class="filter-count" id="f-count">Showing {len(videos)} videos</span>
            </div>
            <div class="filters" style="padding: 10px 18px;">
                <span style="font-size: 13px; font-weight: 600; color: #333;">JTBD:</span>
                {"".join(f'<label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;"><input type="checkbox" class="jtbd-cb" value="{j}" onchange="applyFilters()" style="cursor:pointer;"> {j}</label>' for j in all_jtbd)}
            </div>

            <div id="video-list"></div>
        </div>

        <!-- TAB 2: Competitors -->
        <div id="tab-competitors" class="tab-content">
            <div class="card">
                <h2>👀 Competitor Watch — Past 30 Days</h2>
                <p>Recent uploads from {len(comp_channels)} tracked channels.</p>
            </div>

            <!-- Channel summary cards -->
            <div id="channel-summary" style="margin-bottom: 16px;"></div>

            <div class="filters">
                <span style="font-size: 13px; font-weight: 600; color: #333;">Filter:</span>
                <label>Channel <select id="f-comp-channel" onchange="applyCompFilters()"><option value="all">All ({len(comp_channels)} channels)</option>{"".join(f'<option value="{c}">{c}</option>' for c in comp_channels)}</select></label>
                <label>Period <select id="f-comp-period" onchange="applyCompFilters()"><option value="all">All (30 days)</option><option value="week">Past 7 days</option><option value="month">8-30 days</option></select></label>
                <label>JTBD <select id="f-comp-jtbd" onchange="applyCompFilters()"><option value="all">All</option>{make_options(all_jtbd)}</select></label>
                <span class="filter-count" id="f-comp-count">Showing {len(competitor_videos)} videos</span>
            </div>

            <div id="comp-list"></div>
        </div>
    </div>

    <div class="footer">Generated {date_display} · Retirement Content Trends Dashboard</div>

    <script>
    const videos = {videos_json};
    const compVideos = {comp_json};

    function fmt(n) {{ if (n>=1e6) return (n/1e6).toFixed(1)+'M'; if (n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); }}
    function dur(s) {{ if (!s||s<=0) return ''; var h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60; if(h>0) return h+':'+String(m).padStart(2,'0')+':'+String(sec).padStart(2,'0'); return m+':'+String(sec).padStart(2,'0'); }}
    function ago(d) {{ if(!d) return ''; var diff=Math.floor((new Date()-new Date(d))/(864e5)); return diff+'d ago'; }}

    function renderRow(v, i) {{
        var tags = '';
        if (v.topic) tags += '<span class="tag tag-topic">'+v.topic+'</span>';
        if (v.angle) tags += '<span class="tag tag-angle">'+v.angle+'</span>';
        if (v.content_type) tags += '<span class="tag tag-type">'+v.content_type+'</span>';
        tags += v.is_short ? '<span class="tag tag-short">SHORT</span>' : (v.format==='Livestream' ? '<span class="tag tag-live">LIVE '+dur(v.duration_seconds)+'</span>' : '<span class="tag tag-long">'+dur(v.duration_seconds)+'</span>');
        if (v.language && v.language!=='unknown') tags += '<span class="tag tag-lang">'+v.language.toUpperCase()+'</span>';
        if (v.jtbd && v.jtbd.length) v.jtbd.forEach(function(j){{ tags += '<span class="tag tag-jtbd">'+j+'</span>'; }});

        var html = '<div class="vrow">';
        html += '<div class="vrank">#'+(i+1)+'</div>';
        html += '<div class="vcontent">';
        html += '<a href="'+v.url+'" target="_blank">'+v.title+'</a>';
        html += '<div class="vmeta"><span class="ch">'+v.channel+'</span> · '+fmt(v.view_count)+' views · '+ago(v.published_at)+'</div>';
        html += '<div style="margin-top:4px;">'+tags+'</div>';
        if (v.summary) html += '<div class="vsummary">'+v.summary+'</div>';
        if (v.why_performing) html += '<div class="vwhy">💡 '+v.why_performing+'</div>';
        html += '</div>';
        html += '<div class="vstats">';
        html += '<div class="s"><span class="sv">'+fmt(v.view_count)+'</span><span class="sl">views</span></div>';
        html += '<div class="s"><span class="sv">'+fmt(v.like_count||0)+'</span><span class="sl">likes</span></div>';
        html += '<div class="s"><span class="sv">'+fmt(v.comment_count||0)+'</span><span class="sl">comments</span></div>';
        html += '</div></div>';
        return html;
    }}

    function applyFilters() {{
        var topic = document.getElementById('f-topic').value;
        var format = document.getElementById('f-format').value;
        var lang = document.getElementById('f-lang').value;
        var checkedJtbd = Array.from(document.querySelectorAll('.jtbd-cb:checked')).map(function(cb){{ return cb.value; }});

        var f = videos;
        if (topic!=='all') f = f.filter(function(v){{ return v.topic===topic; }});
        if (format!=='all') f = f.filter(function(v){{ return v.format===format; }});
        // Language: "en" = English only, "all" = everything
        if (lang==='en') f = f.filter(function(v){{ return v.language==='en'; }});
        // JTBD: OR logic — video must have at least one of the checked tags
        if (checkedJtbd.length > 0) {{
            f = f.filter(function(v){{
                if (!v.jtbd) return false;
                return checkedJtbd.some(function(j){{ return v.jtbd.indexOf(j) !== -1; }});
            }});
        }}
        document.getElementById('f-count').textContent = 'Showing '+f.length+' videos';
        var html = '';
        if (f.length===0) html = '<p style="color:#999;padding:20px;">No videos match filters.</p>';
        else f.forEach(function(v,i){{ html += renderRow(v,i); }});
        document.getElementById('video-list').innerHTML = html;
    }}

    function applyCompFilters() {{
        var ch = document.getElementById('f-comp-channel').value;
        var period = document.getElementById('f-comp-period').value;
        var jtbd = document.getElementById('f-comp-jtbd').value;
        var f = compVideos;
        if (ch!=='all') f = f.filter(function(v){{ return v.channel===ch; }});
        if (period!=='all') f = f.filter(function(v){{ return v.period===period; }});
        if (jtbd!=='all') f = f.filter(function(v){{ return v.jtbd && v.jtbd.indexOf(jtbd)!==-1; }});
        document.getElementById('f-comp-count').textContent = 'Showing '+f.length+' videos';
        var html = '';
        if (f.length===0) html = '<p style="color:#999;padding:20px;">No videos match filters.</p>';
        else f.forEach(function(v,i){{ html += renderRow(v,i); }});
        document.getElementById('comp-list').innerHTML = html;
    }}

    function renderChannelSummary() {{
        // Build per-channel stats
        var channels = {{}};
        compVideos.forEach(function(v) {{
            if (!channels[v.channel]) channels[v.channel] = {{ week: 0, month: 0, total: 0, views: 0, topics: {{}}, jtbds: {{}} }};
            var c = channels[v.channel];
            c.total++;
            c.views += v.view_count;
            if (v.period === 'week') c.week++; else c.month++;
            if (v.topic) c.topics[v.topic] = (c.topics[v.topic] || 0) + 1;
            if (v.jtbd) v.jtbd.forEach(function(j) {{ c.jtbds[j] = (c.jtbds[j] || 0) + 1; }});
        }});

        var sorted = Object.keys(channels).sort(function(a,b) {{ return channels[b].views - channels[a].views; }});
        var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:10px;">';
        sorted.forEach(function(name) {{
            var c = channels[name];
            var topTopics = Object.entries(c.topics).sort(function(a,b){{return b[1]-a[1];}}).slice(0,3).map(function(e){{return e[0];}});
            var topJtbd = Object.entries(c.jtbds).sort(function(a,b){{return b[1]-a[1];}}).slice(0,3).map(function(e){{return e[0];}});
            html += '<div style="background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:14px;">';
            html += '<div style="font-weight:600;font-size:14px;color:#1a5276;margin-bottom:6px;">'+name+'</div>';
            html += '<div style="font-size:12px;color:#666;">';
            html += '<span style="font-weight:600;">'+c.week+'</span> this week · <span style="font-weight:600;">'+c.total+'</span> this month · '+fmt(c.views)+' total views';
            html += '</div>';
            if (topTopics.length) html += '<div style="margin-top:6px;">'+topTopics.map(function(t){{return '<span class="tag tag-topic">'+t+'</span>';}}).join('')+'</div>';
            if (topJtbd.length) html += '<div style="margin-top:4px;">'+topJtbd.map(function(j){{return '<span class="tag tag-jtbd">'+j+'</span>';}}).join('')+'</div>';
            html += '</div>';
        }});
        html += '</div>';
        document.getElementById('channel-summary').innerHTML = html;
    }}

    function switchTab(name) {{
        document.querySelectorAll('.tab').forEach(function(t){{ t.classList.remove('active'); }});
        document.querySelectorAll('.tab-content').forEach(function(t){{ t.classList.remove('active'); }});
        if (name==='trending') {{
            document.querySelectorAll('.tab')[0].classList.add('active');
            document.getElementById('tab-trending').classList.add('active');
        }} else {{
            document.querySelectorAll('.tab')[1].classList.add('active');
            document.getElementById('tab-competitors').classList.add('active');
        }}
    }}

    // Initial render
    applyFilters();
    applyCompFilters();
    renderChannelSummary();
    </script>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="YouTube Trends Dashboard")
    parser.add_argument("--preview", action="store_true", help="Open in browser")
    args = parser.parse_args()

    if not os.environ.get("YOUTUBE_API_KEY"):
        logger.error("YOUTUBE_API_KEY required. Get one at https://console.cloud.google.com")
        sys.exit(1)

    today = datetime.now(timezone.utc)
    date_str = today.strftime("%Y-%m-%d")
    date_display = today.strftime("%A, %B %d, %Y")

    logger.info("📺 Fetching trending videos...")
    yt_data = gather_youtube_trends()

    logger.info("👀 Fetching competitor videos...")
    comp_videos = gather_competitor_videos()

    logger.info("🎨 Generating dashboard...")
    html = generate_dashboard(yt_data, comp_videos, date_display)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    dashboard_file = output_dir / "dashboard.html"
    dashboard_file.write_text(html, encoding="utf-8")
    logger.info("💾 Saved to %s", dashboard_file)

    # --- Snapshot system ---
    # Always save a timestamped snapshot (never overwritten).
    # Also maintain a "latest" symlink-style file for convenience.
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    new_data = {"trends": yt_data, "competitors": comp_videos, "generated_at": now_ts}
    has_data = (
        len(yt_data.get("videos", [])) > 0
        or len(comp_videos) > 0
    )

    if has_data:
        # Save timestamped snapshot
        snapshot_file = data_dir / f"snapshot-{now_ts}.json"
        snapshot_file.write_text(
            json.dumps(new_data, indent=2, default=str), encoding="utf-8"
        )
        logger.info("💾 Snapshot saved to %s", snapshot_file)

        # Update latest pointer
        latest_file = data_dir / "latest.json"
        latest_file.write_text(
            json.dumps(new_data, indent=2, default=str), encoding="utf-8"
        )
        logger.info("💾 Latest data updated")
    else:
        logger.warning("No data fetched — skipping snapshot to preserve history")
        # Try to rebuild dashboard from latest snapshot
        latest_file = data_dir / "latest.json"
        if latest_file.exists():
            try:
                old = json.loads(latest_file.read_text(encoding="utf-8"))
                old_trends = old.get("trends", {})
                old_comp = old.get("competitors", [])
                if len(old_trends.get("videos", [])) > 0 or len(old_comp) > 0:
                    logger.info(
                        "Rebuilding dashboard from last good snapshot (%s)",
                        old.get("generated_at", "unknown"),
                    )
                    html = generate_dashboard(old_trends, old_comp, date_display)
                    dashboard_file.write_text(html, encoding="utf-8")
            except (json.JSONDecodeError, KeyError):
                pass

    if args.preview:
        webbrowser.open(f"file://{dashboard_file.resolve()}")
        logger.info("🌐 Opened in browser")

    logger.info("🎉 Done!")


if __name__ == "__main__":
    main()
