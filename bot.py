import keep_alive
keep_alive.start()

import os
import asyncio
import datetime
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, filters)
import db
from language import t
from cv_matcher import match_jobs
from online_work import get_category

TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "0").split(",")))
BOT_USERNAME = "MUYA_NET_Bot"
YOUTUBE_GUIDE_URL = "https://www.youtube.com/@MUYA_NET"

CV_FIELDS    = ["full_name","email","phone","location","summary",
                "education","experience","skills","languages"]
CV_QUESTIONS = ["cv_q1","cv_q2","cv_q3","cv_q4","cv_q5",
                "cv_q6","cv_q7","cv_q8","cv_q9"]

def _b(label, cb):  return InlineKeyboardButton(label, callback_data=cb)
def _url(label, u): return InlineKeyboardButton(label, url=u)
def _back(cb, lng): return _b(t(lng, "back"), cb)

def _fmt_job(j, lng):
    today = str(datetime.date.today())
    status = t(lng, "open") if str(j.get("deadline", "")) >= today else t(lng, "closed")
    return (
        f"📋 *{j.get('title','N/A')}*\n\n"
        f"🏢 *Company:* {j.get('company','N/A')}\n"
        f"📍 *Location:* {j.get('location','N/A')}\n"
        f"📂 *Category:* {j.get('category','N/A')}\n"
        f"⏳ *Deadline:* {j.get('deadline','N/A')} ({status})\n"
        f"📝 *Description:* {j.get('description','No details specified.')}\n\n"
        f"🌐 *Source:* {j.get('source','N/A')}"
    )

def _job_keyboard(j, lng, back_cb="main_menu"):
    url = str(j.get("apply_url", "#"))
    return InlineKeyboardMarkup([
        [_url(t(lng, "apply"), url)],
        [_b(t(lng, "track"), f"track:{j.get('id')}")],
        [_back(back_cb, lng)]
    ])

async def _guard(upd: Update, ctx):
    u = upd.effective_user
    if not u: return False
    if db.is_banned(u.id):
        if upd.message:
            await upd.message.reply_text("🚫 Access Denied: Account Restrained.")
        elif upd.callback_query:
            await upd.callback_query.answer("🚫 Account restricted by administration.", show_alert=True)
        return False
    if db.get_maintenance() and u.id not in ADMIN_IDS:
        m_msg = "🔧 MUYA_NET is currently undergoing system optimization. Please return later."
        if upd.message:
            await upd.message.reply_text(m_msg)
        elif upd.callback_query:
            await upd.callback_query.message.edit_text(m_msg)
        return False
    return True

async def start(upd: Update, ctx):
    uid = upd.effective_user.id
    db.register_user(uid, upd.effective_user.username or "", upd.effective_user.full_name or "")
    if not await _guard(upd, ctx): return
    kbd = InlineKeyboardMarkup([
        [_b("English", "set_lang:en"), _b("አማርኛ", "set_lang:am")]
    ])
    await upd.message.reply_text(t("en", "welcome"), parse_mode="Markdown", reply_markup=kbd)

async def show_main(upd: Update, ctx, lng):
    kbd = InlineKeyboardMarkup([
        [_b(t(lng, "browse"), "browse"), _b(t(lng, "search"), "search_prompt")],
        [_b(t(lng, "online"), "online_menu"), _b(t(lng, "alerts"), "alerts_menu")],
        [_b(t(lng, "mycv"), "cv_menu"), _b(t(lng, "lang"), "change_lang")]
    ])
    msg = t(lng, "main_menu")
    if upd.message:
        await upd.message.reply_text(msg, parse_mode="Markdown", reply_markup=kbd)
    elif upd.callback_query:
        await upd.callback_query.message.edit_text(msg, parse_mode="Markdown", reply_markup=kbd)

async def cmd_admin(upd: Update, ctx):
    if upd.effective_user.id not in ADMIN_IDS: return
    await upd.message.reply_text(
        "🛠 *MUYA_NET  Control Terminal*", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [_b("📊 Operational Status", "adm:status"), _b("📢 Broadcast Global", "adm:bc_all")],
            [_b("🎯 Broadcast By ID", "adm:bc_select"), _b("🔑 Broadcast By Keyword", "adm:bc_kw")],
            [_b("🔧 Activate Maint Mode", "adm:m_on"), _b("✅ Resume Standard Ops", "adm:m_off")],
            [_b("🚫 Enforce Account Ban", "adm:ban_id"), _b("✅ Lift Account Restriction", "adm:unban_id")]
        ]))

async def cb_handler(upd: Update, ctx):
    q = upd.callback_query
    uid = q.from_user.id
    lng = db.get_lang(uid) or "en"
    await q.answer()

    if q.data.startswith("adm:") and uid in ADMIN_IDS:
        action_flag = q.data.split(":", 1)[1]
        if action_flag == "status":
            u_c, b_c, j_c, s_c = db.stats()
            m_s = "ACTIVE ⚠️" if db.get_maintenance() else "INACTIVE ✅"
            await q.message.reply_text(
                f"📊 *MUYA_NET System Matrix Status*\n\n"
                f"• Registered Node Entities: `{u_c}`\n"
                f"• Restrained Core Channels: `{b_c}`\n"
                f"• Database Job Postings: `{j_c}`\n"
                f"• Active Subscriptions/Alerts: `{s_c}`\n"
                f"• Global Maintenance Block: *{m_s}*", parse_mode="Markdown")
        elif action_flag == "bc_all":
            ctx.user_data["action"] = "broadcast"
            await q.message.reply_text("📢 Supply text payload for global platform transmission:")
        elif action_flag == "bc_select":
            ctx.user_data["action"] = "broadcast_selected"
            await q.message.reply_text("🎯 Supply discrete payloads following layout format:\n`ID1,ID2 : Text message layout block here`")
        elif action_flag == "bc_kw":
            ctx.user_data["action"] = "broadcast_keyword"
            await q.message.reply_text("🔑 Supply keyword broadcast following layout format:\n`Keyword : Message text here`\n*(Example: python : We just posted a new Python job!)*")
        elif action_flag == "ban_id":
            ctx.user_data["action"] = "ban"
            await q.message.reply_text("🚫 Enter target structural Telegram ID numerical variable to restrict:")
        elif action_flag == "unban_id":
            ctx.user_data["action"] = "unban"
            await q.message.reply_text("✅ Enter target structural Telegram ID numerical variable to restore:")
        elif action_flag == "m_on":
            db.set_maintenance(True)
            await q.message.reply_text("🔧 Maintenance constraint arrays mapped *ON*.")
        elif action_flag == "m_off":
            db.set_maintenance(False)
            await q.message.reply_text("✅ Maintenance constraint arrays mapped *OFF*.")
        return

    if not await _guard(upd, ctx): return

    if q.data.startswith("set_lang:"):
        new_lng = q.data.split(":")[1]
        db.set_lang(uid, new_lng)
        await show_main(upd, ctx, new_lng)
        
    elif q.data == "change_lang":
        kbd = InlineKeyboardMarkup([
            [_b("English", "set_lang:en"), _b("አማርኛ", "set_lang:am")],
            [_back("main_menu", lng)]
        ])
        await q.message.edit_text("🌐 Choose Your Language / ቋንቋ ይምረጡ:", reply_markup=kbd)
        
    elif q.data == "main_menu":
        ctx.user_data["action"] = None
        await show_main(upd, ctx, lng)
        
    elif q.data == "browse":
        cats = db.all_categories()
        if not cats:
            await q.message.edit_text(t(lng, "no_cats"), reply_markup=InlineKeyboardMarkup([[_back("main_menu", lng)]]))
            return
        rows = [[_b(c, f"cat:{c}")] for c in cats]
        rows.append([_back("main_menu", lng)])
        await q.message.edit_text(t(lng, "cats_title"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        
    elif q.data.startswith("cat:"):
        cat_name = q.data.split(":", 1)[1]
        jobs = db.jobs_by_category(cat_name)
        if not jobs:
            await q.message.edit_text(t(lng, "no_jobs"), reply_markup=InlineKeyboardMarkup([[_back("browse", lng)]]))
            return
        await q.message.delete()
        for j in jobs[:5]:
            await ctx.bot.send_message(uid, _fmt_job(j, lng), parse_mode="Markdown", reply_markup=_job_keyboard(j, lng, back_cb="browse"))
        await ctx.bot.send_message(uid, t(lng, "listings_end"), reply_markup=InlineKeyboardMarkup([[_back("browse", lng)]]))
        
    elif q.data == "search_prompt":
        ctx.user_data["action"] = "search"
        await q.message.edit_text(t(lng, "search_prompt"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[_back("main_menu", lng)]]))
        
    elif q.data.startswith("track:"):
        jid = q.data.split(":")[1]
        db.record_apply(uid, jid)
        await q.answer(t(lng, "app_saved"))
        
    elif q.data == "online_menu":
        rows = [
            [_b(t(lng, "online_freelance"), "owi:freelance"), _b(t(lng, "online_remote"), "owi:remote")],
            [_b(t(lng, "online_airdrop"), "owi:airdrop"), _b(t(lng, "online_microtask"), "owi:microtask")],
            [_b(t(lng, "online_survey"), "owi:survey"), _b(t(lng, "online_youtube"), "owi:youtube")],
            [_b(t(lng, "video_guide"), "video_guide"), _b(t(lng, "share_bot"), "share_bot")],
            [_back("main_menu", lng)]
        ]
        await q.message.edit_text(t(lng, "online_title"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        
    elif q.data.startswith("owi:"):
        ckey = q.data.split(":")[1]
        cat = get_category(ckey)
        await q.message.delete()
        for i in cat.get("items", []):
            m = f"⭐ *{i['name']}*\n{i['desc']}\n\n_{i['tips']}_"
            await ctx.bot.send_message(uid, m, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
                [_url(t(lng, "open_link"), i["url"])],
                [_back("online_menu", lng)]
            ]))
        await ctx.bot.send_message(uid, t(lng, "listings_end"), reply_markup=InlineKeyboardMarkup([[_back("online_menu", lng)]]))
        
    elif q.data == "alerts_menu":
        
        kbd = InlineKeyboardMarkup([
            [_b(t(lng, "sub_cat"), "sub_cats"), _b(t(lng, "add_kw"), "add_kw")],
            [_b(t(lng, "my_subs"), "my_subs"), _back("main_menu", lng)]
        ])
        await q.message.edit_text(t(lng, "alert_title"), parse_mode="Markdown", reply_markup=kbd)

    elif q.data == "sub_cats":
        cats = db.all_categories()
        rows = [[_b(c, f"sub:{c}")] for c in cats]
        rows.append([_back("alerts_menu", lng)])
        await q.message.edit_text(t(lng, "cats_title"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        
    elif q.data.startswith("sub:"):
        cat_name = q.data.split(":", 1)[1]
        if db.add_subscription(uid, cat_name):
            await q.message.edit_text(t(lng, "sub_saved", cat=cat_name), reply_markup=InlineKeyboardMarkup([[_back("alerts_menu", lng)]]))
        else:
            await q.message.edit_text(t(lng, "sub_exists", cat=cat_name), reply_markup=InlineKeyboardMarkup([[_back("alerts_menu", lng)]]))
            
    elif q.data == "my_subs":
        kws = db.user_keywords(uid)
        cats = db.user_subscriptions(uid)
        if not kws and not cats:
            await q.message.edit_text(t(lng, "no_subs"), reply_markup=InlineKeyboardMarkup([[_back("alerts_menu", lng)]]))
            return
        m = "📋 *Active Watch Configurations:*\n\n" if lng == "en" else "📋 *ንቁ የክትትል ማሳወቂያዎቼ:*\n\n"
        rows = []
        for c in cats:
            m += f"📂 Category: {c}\n" if lng == "en" else f"📂 ምድብ: {c}\n"
            rows.append([_b(f"❌ Remove {c}", f"unsub:{c}")])
        for k in kws:
            m += f"🔑 Keyword: {k}\n" if lng == "en" else f"🔑 ቃል: {k}\n"
            rows.append([_b(f"❌ Remove {k}", f"unkw:{k}")])
        rows.append([_back("alerts_menu", lng)])
        await q.message.edit_text(m, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        
    elif q.data.startswith("unsub:"):
        cat_name = q.data.split(":", 1)[1]
        db._del2("subscriptions", "user_id", str(uid), "category", cat_name)
        await q.message.edit_text(t(lng, "unsub_done", cat=cat_name), reply_markup=InlineKeyboardMarkup([[_back("my_subs", lng)]]))
        
    elif q.data.startswith("unkw:"):
        kw = q.data.split(":", 1)[1]
        db.remove_keyword(uid, kw)
        await q.message.edit_text(f"✅ Removed: {kw}", reply_markup=InlineKeyboardMarkup([[_back("my_subs", lng)]]))
        
    elif q.data == "add_kw":
        ctx.user_data["action"] = "add_kw"
        await q.message.edit_text(t(lng, "kw_prompt"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[_back("alerts_menu", lng)]]))
        
    elif q.data == "cv_menu":
        kbd = InlineKeyboardMarkup([
            [_b(t(lng, "create_cv"), "cv_create"), _b(t(lng, "view_cv"), "cv_view")],
            [_b(t(lng, "match"), "cv_match"), _back("main_menu", lng)]
        ])
        await q.message.edit_text(t(lng, "cv_title"), parse_mode="Markdown", reply_markup=kbd)
        
    elif q.data == "cv_create":
        ctx.user_data["cv_step"] = 0
        ctx.user_data["payload"] = {}
        await q.message.edit_text(t(lng, CV_QUESTIONS[0]), parse_mode="Markdown")
        
    elif q.data == "cv_view":
        cv = db.get_cv(uid)
        if not cv:
            await q.message.edit_text(t(lng, "cv_none"), reply_markup=InlineKeyboardMarkup([[_back("cv_menu", lng)]]))
            return
        m = (
            f"👤 *Name:* {cv.get('full_name')}\n"
            f"✉️ *Email:* {cv.get('email')}\n"
            f"📞 *Phone:* {cv.get('phone')}\n"
            f"📍 *Location:* {cv.get('location')}\n"
            f"📝 *Summary:* {cv.get('summary')}\n"
            f"🎓 *Education:* {cv.get('education')}\n"
            f"💼 *Experience:* {cv.get('experience')}\n"
            f"🛠 *Skills:* {cv.get('skills')}\n"
            f"🌐 *Languages:* {cv.get('languages')}"
        )
        await q.message.edit_text(m, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[_back("cv_menu", lng)]]))
        
    elif q.data == "cv_match":
        await q.message.edit_text(t(lng, "matching"), parse_mode="Markdown")
        matches = match_jobs(uid)
        if not matches:
            await q.message.edit_text(t(lng, "no_matches"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[_back("cv_menu", lng)]]))
            return
        await q.message.delete()
        await ctx.bot.send_message(uid, t(lng, "top_matches"), parse_mode="Markdown")
        for j in matches[:5]:
            await ctx.bot.send_message(uid, _fmt_job(j, lng), parse_mode="Markdown", reply_markup=_job_keyboard(j, lng, back_cb="cv_menu"))
        await ctx.bot.send_message(uid, t(lng, "listings_end"), reply_markup=InlineKeyboardMarkup([[_back("cv_menu", lng)]]))
        
    elif q.data == "video_guide":
        await q.message.edit_text(t(lng, "video_guide"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
            [_url(t(lng, "watch_video"), YOUTUBE_GUIDE_URL)], 
            [_back("online_menu", lng)]
        ]))
        
    elif q.data == "share_bot":
        share_txt = f"Find jobs from trusted platforms using this bot! t.me/{BOT_USERNAME}"
        if lng == "am":
            share_txt = f"ሙያኔት  ቦትን በመጠቀም በቀላሉ ከታማኝ ምንጮች የተለያዩ የስራ እድሎችን በነፃ ያግኙ! t.me/{BOT_USERNAME}"
        enc_txt = urllib.parse.quote(share_txt)
        valid_share_url = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}&text={enc_txt}"
        await q.message.edit_text(t(lng, "share_bot"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
            [_url(t(lng, "share_bot"), valid_share_url)], 
            [_back("online_menu", lng)]
        ]))

async def text_handler(upd: Update, ctx):
    uid = upd.effective_user.id
    txt = upd.message.text.strip() if upd.message.text else ""
    if not txt: return
    
    act = ctx.user_data.get("action")
    step = ctx.user_data.get("cv_step")
    lng = db.get_lang(uid) or "en"

    if uid in ADMIN_IDS and act in ["broadcast", "broadcast_selected", "broadcast_keyword", "ban", "unban"]:
        ctx.user_data["action"] = None
        
        if act == "broadcast":
            users = db.get_all_users()
            await upd.message.reply_text(f"📢 Transferring payload matrix to {len(users)} connections...")
            count = 0
            for u in users:
                try:
                    await ctx.bot.send_message(chat_id=int(u.get("id")), text=f"📢 *MUYA_NET*\n\n{txt}", parse_mode="Markdown")
                    count += 1
                    await asyncio.sleep(0.05)
                except: pass
            await upd.message.reply_text(f"✅ Packet broadcast concluded to {count} active channels.")
            
        elif act == "broadcast_selected":
            if ":" not in txt:
                await upd.message.reply_text("❌ Input structural layout constraint mismatch. Syntactic rule: `ID1,ID2 : Message text here`")
                return
            ids_blob, body = txt.split(":", 1)
            try:
                targets = [int(i.strip()) for i in ids_blob.split(",") if i.strip().isdigit()]
            except:
                await upd.message.reply_text("❌ Numeric data parsing array fault.")
                return
            await upd.message.reply_text(f"🎯 Directing unique streams to {len(targets)} channels...")
            count = 0
            for t_id in targets:
                try:
                    await ctx.bot.send_message(chat_id=t_id, text=f"📢 *MUYA_NET*\n\n{body.strip()}", parse_mode="Markdown")
                    count += 1
                    await asyncio.sleep(0.05)
                except: pass
            await upd.message.reply_text(f"✅ Targeted pipeline sequence processed to {count}/{len(targets)} targets.")

        elif act == "broadcast_keyword":
          
            if ":" not in txt:
                await upd.message.reply_text("❌ Syntactic rule error. Format must be: `Keyword : Message here`")
                return
            
            kw_target, body = txt.split(":", 1)
            kw_target = kw_target.strip().lower()
            body = body.strip()
            
            users = db.get_all_users()
            count = 0
            await upd.message.reply_text(f"🎯 Scanning database for users watching the keyword or category: '{kw_target}'...")
            
            for u in users:
                target_uid = int(u.get("id"))
                user_kws = [k.lower() for k in db.user_keywords(target_uid)]
                user_cats = [c.lower() for c in db.user_subscriptions(target_uid)]
                
                if kw_target in user_kws or kw_target in user_cats:
                    try:
                        await ctx.bot.send_message(chat_id=target_uid, text=f"🔔 *MUYA_NET_Alert*\n\n{body}", parse_mode="Markdown")
                        count += 1
                        await asyncio.sleep(0.05)
                    except: pass
                    
            await upd.message.reply_text(f"✅ Keyword payload successfully delivered to {count} matched channels.")
            
        elif act == "ban":
            if not txt.isdigit():
                await upd.message.reply_text("❌ Target string data error. Requires numeric parameter ID.")
                return
            db.ban_user(int(txt))
            await upd.message.reply_text(f"🚫 Active database blocks built over ID: `{txt}`", parse_mode="Markdown")
            
        elif act == "unban":
            if not txt.isdigit():
                await upd.message.reply_text("❌ Target string data error. Requires numeric parameter ID.")
                return
            db.unban_user(int(txt))
            await upd.message.reply_text(f"✅ Clearance verified. Restriction dropped for ID: `{txt}`", parse_mode="Markdown")
        return

    if not await _guard(upd, ctx): return

    if act == "search":
        ctx.user_data["action"] = None
        res = db.search_jobs(txt)
        if not res:
            await upd.message.reply_text(t(lng, "no_results", q=txt), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[_b("🏠 Menu", "main_menu")]]))
            return
        await upd.message.reply_text(t(lng, "found", n=len(res), q=txt), parse_mode="Markdown")
        for j in res[:5]:
            await upd.message.reply_text(_fmt_job(j, lng), parse_mode="Markdown", reply_markup=_job_keyboard(j, lng, back_cb="main_menu"))
        return

    if act == "add_kw":
        ctx.user_data["action"] = None
        if db.add_keyword(uid, txt):
            await upd.message.reply_text(t(lng, "kw_saved", kw=txt), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[_back("alerts_menu", lng)]]))
        else:
            await upd.message.reply_text(t(lng, "kw_exists", kw=txt), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[_back("alerts_menu", lng)]]))
        return

    if step is not None:
        ctx.user_data["payload"][CV_FIELDS[step]] = txt
        step += 1
        if step >= len(CV_FIELDS):
            ctx.user_data["cv_step"] = None
            db.save_cv(uid, ctx.user_data["payload"])
            await upd.message.reply_text(t(lng, "cv_saved"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[_b("🏠 Menu", "main_menu")]]))
        else:
            ctx.user_data["cv_step"] = step
            await upd.message.reply_text(t(lng, CV_QUESTIONS[step]), parse_mode="Markdown")
        return

    await show_main(upd, ctx, lng)

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🚀 System Live Engine Online. Brand Profile: MUYA_NET...")
    app.run_polling()

if __name__ == "__main__":
    main()
