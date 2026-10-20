"""Transport-independent private-chat conversations. No network or clinical decisions."""
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied, ObjectDoesNotExist
from django.db import transaction
from .models import *
from .services import *
from .access import assignments, cases_for, has_role, officer_active

WELCOME = 'Selamat datang di SALAM MANIS.\nSadar Lapor Mandiri – Akses Mudah, Aman, Humanis.\n\nMendekatkan Akses, Menghubungkan Layanan.\n\nSilakan pilih akses Anda.'
INTRO = 'SALAM MANIS merupakan layanan yang memudahkan masyarakat mengakses wajib lapor dan rehabilitasi narkotika melalui titik akses yang terhubung dengan BNN Kota Surabaya dan jejaring layanan.\n\nAnda dapat melakukan registrasi, menyampaikan kendala atau permasalahan terkait narkotika, memperoleh informasi titik akses, serta memantau progres permohonan.'
PUBLIC = [('Baca Ketentuan SALAM MANIS','terms'),('Registrasi Pemohon','register'),('Skrining','screen'),('Titik Akses SALAM MANIS','directory'),('Self Asesmen','self'),('Progres Permohonan Saya','progress'),('Kembali ke Menu Awal','home')]
ADMIN = [('Ringkasan Permohonan','admin_summary'),('Daftar Pemohon','admin_list'),('Permohonan Menunggu Tindak Lanjut','admin_pending'),('Perbarui Progres','admin_update'),('Buka Dashboard','dashboard'),('Profil dan Lokasi Penugasan','admin_profile'),('Kembali ke Menu Awal','home')]
BACK = [('Menu Masyarakat','public')]
DRAFT_NAV = [('Kembali ke Isian Sebelumnya','previous'),('Simpan dan Lanjutkan Nanti','save'),('Batalkan Pengisian','cancel')]

def reply(text, buttons=()):
    icons = {'public':'👥','admin':'🧑‍💼','terms':'📋','register':'📝','screen':'💬','directory':'📍','self':'🌿','progress':'📬','home':'🏠','save':'💾','submit':'✅','notify':'🔔','dashboard':'🖥','admin_list':'📂','admin_summary':'📊','admin_profile':'👤'}
    return {'text':text,'buttons':[[f'{icons.get(action, "")} {label}'.strip(),action] for label,action in buttons]}

def set_state(user, **state):
    user.state = state
    user.save(update_fields=['state'])

def masked(data):
    return '\n'.join(f'{label}: {("************" + value[-4:]) if key == "nik" else value}' for key,label in FIELDS if (value:=data.get(key,''))) + '\nAlamat input manual, belum terverifikasi. NIK hanya diperiksa formatnya.'

def draft_prompt(draft):
    key, label = FIELDS[draft.step]
    hint = {'nik':'16 digit; bukan verifikasi Dukcapil.','phone':'Nomor yang dapat dihubungi; gunakan 08… atau kode negara +….','city':'Input manual kota/kabupaten domisili; alamat belum terverifikasi.','district':'Input manual kecamatan domisili.','village':'Input manual kelurahan/desa domisili.','rt':'Angka; nol di depan akan disimpan.','rw':'Angka; nol di depan akan disimpan.'}.get(key,'Isi dengan benar dan lengkap.')
    return reply(f'📝 LANGKAH 1/3 · DATA DIRI\n{"▰" * draft.step}{"▱" * (9-draft.step)}\n\nIsian {draft.step+1}/9 — {label}\n{hint}',DRAFT_NAV)

def summary(draft):
    return reply('✨ Hampir selesai! Periksa data diri Anda.\n\n'+masked(draft.data), [('Ubah Data','edit'),('Kirim Registrasi','submit'),('Simpan Draft','save')])

def user_officer(user): return Officer.objects.filter(telegram=user,verified=True).first()

def directory(category):
    if category not in Category.values or category==Category.COORD: raise ValidationError('Kategori tidak tersedia.')
    locations = Location.objects.filter(category=category,active=True).order_by('name')
    text = f'Data titik akses kategori {category} sedang disiapkan. Silakan periksa kembali secara berkala.'
    if locations.exists():
        text = '\n\n'.join('\n'.join(filter(None,[x.name,x.address,', '.join(filter(None,[x.city,x.district,x.village])),x.contact,x.hours,x.map_url,x.ibm_ap if x.category==Category.VILLAGE else ''])) for x in locations)
    return reply(text,[('Kembali ke Titik Akses','directory'),*BACK])

@transaction.atomic
def handle_update(update_id, telegram_id, text='', action='', private=True, photo=None):
    if not private: return [reply('Gunakan percakapan pribadi dengan bot SALAM MANIS.')]
    cached = BotUpdate.objects.filter(update_id=update_id).first()
    if cached: return cached.replies
    user,_ = TelegramUser.objects.get_or_create(telegram_id=telegram_id)
    user = TelegramUser.objects.select_for_update().get(pk=user.pk)
    cached = BotUpdate.objects.filter(update_id=update_id).first()
    if cached: return cached.replies
    try:
        # Savepoint rolls back failed operations, while retaining a safe response.
        with transaction.atomic():
            responses = dispatch(user,text,action,photo)
    except (ValidationError, PermissionDenied, ObjectDoesNotExist, ValueError, IndexError) as exc:
        if isinstance(exc, PermissionDenied): message = 'Anda tidak memiliki akses untuk tindakan ini.'
        elif isinstance(exc, (ObjectDoesNotExist, ValueError, IndexError)): message = 'Tahap atau pilihan tidak tersedia. Silakan buka kembali menu yang diperlukan.'
        else: message = ' '.join(exc.messages)
        responses = [reply(message,[('Baca Ketentuan SALAM MANIS','terms'),('Registrasi Pemohon','register'),*BACK])]
    BotUpdate.objects.create(update_id=update_id,replies=responses)
    return responses

def dispatch(user, text, action, photo=None):
    state = user.state
    if text == '/start' or action=='home':
        # Leave persistent draft and conversation state intact.
        return [reply('🌿 '+WELCOME+'\n\nKami mendampingi Anda melalui 3 langkah: data diri → kendala → Self Asesmen & bukti.',[('Masyarakat','public'),('Admin','admin')])]
    if action=='public':
        set_state(user,mode='menu')
        result = [reply(INTRO, PUBLIC)]
        if RegistrationDraft.objects.filter(user=user,form_status='DRAFT_REGISTRASI').exists():
            result.append(reply('Ada formulir tersimpan. Lanjutkan pengisian?', [('Lanjutkan Draft','resume'),*BACK]))
        if ScreeningDraft.objects.filter(application__applicant__user=user,application__status__in=[Status.WAIT_SCREEN,Status.NEED_INFO]).exists():
            result.append(reply('Ada draft Skrining tersimpan.', [('Lanjutkan Skrining','screen'),*BACK]))
        return result
    if action=='terms':
        terms = Terms.objects.filter(active=True).first()
        if not terms: return [reply('Ketentuan belum diterbitkan pengelola. Registrasi belum dapat dikirim.',BACK)]
        return [reply(f'Ketentuan SALAM MANIS — versi {terms.version}\n\n{terms.body}', [('Saya Memahami dan Menyetujui',f'agree:{terms.pk}'),('Kembali','public')])]
    if action.startswith('agree:'):
        terms = Terms.objects.filter(pk=action.split(':')[1],active=True).first()
        if not terms: raise ValidationError('Versi ketentuan telah berubah. Silakan baca kembali.')
        Consent.objects.get_or_create(user=user,terms=terms)
        return [reply('Persetujuan versi ketentuan dan waktunya telah dicatat.',[('Registrasi Pemohon','register'),('Lanjutkan Draft','resume'),*BACK])]
    if action in ('register','resume'):
        if not user.notification_decided:
            return [reply('🔔 Agar Anda langsung mengetahui pembaruan, izinkan bot mengirim pemberitahuan layanan. Pesan tidak memuat NIK atau isi kendala. Anda dapat menonaktifkannya kapan saja.', [('Setuju & lanjut registrasi','notify_register'),('Lanjut tanpa notifikasi','notify_skip')])]
        app = active_application(user)
        if app:
            if app.status == Status.WAIT_SCREEN: return dispatch(user,'','screen')
            if app.status in (Status.WAIT_ASSESS,Status.WAIT_PROOF): return dispatch(user,'','self')
            return [reply('📂 Anda sudah memiliki permohonan aktif. Silakan lanjutkan dari tahap terakhir.',[('Progres Permohonan Saya','progress'),('Skrining','screen'),*BACK])]
        draft,_ = RegistrationDraft.objects.get_or_create(user=user)
        if draft.form_status=='REGISTRASI_TERKIRIM':
            draft.data={}; draft.step=0; draft.editing=False; draft.form_status='DRAFT_REGISTRASI'; draft.save()
        set_state(user,mode='registration')
        return [summary(draft) if draft.step>=len(FIELDS) else draft_prompt(draft)]
    if action in ('save','cancel','previous','edit','submit') or action.startswith('field:'):
        if action=='submit' and active_application(user):
            return [reply('Permohonan sudah tersimpan.',[('Progres Permohonan Saya','progress'),('Skrining','screen'),*BACK])]
        draft = RegistrationDraft.objects.get(user=user,form_status='DRAFT_REGISTRASI')
        if action=='cancel':
            set_state(user,mode='menu')
            return [reply('Batalkan hanya formulir yang belum dikirim?', [('Ya, Batalkan Draft','confirm_cancel'),('Lanjutkan Draft','resume')])]
        if action=='save':
            set_state(user,mode='menu')
            return [reply('Draft tersimpan. Anda dapat melanjutkannya kapan saja.',[('Lanjutkan Draft','resume'),*BACK])]
        if action=='previous':
            draft.step=max(0,min(draft.step-1,len(FIELDS)-1)); draft.editing=False; draft.save()
            set_state(user,mode='registration')
            return [draft_prompt(draft)]
        if action=='edit': return [reply('Pilih field yang ingin diubah.',[(label,f'field:{key}') for key,label in FIELDS])]
        if action.startswith('field:'):
            key=action.split(':')[1]
            if key not in dict(FIELDS): raise ValidationError('Field tidak tersedia.')
            draft.step=[x[0] for x in FIELDS].index(key); draft.editing=True; draft.save()
            set_state(user,mode='registration')
            return [draft_prompt(draft)]
        if action=='submit':
            app,created=submit_registration(user)
            set_state(user,mode='menu')
            responses=[reply(SUCCESS,[('Skrining','screen'),('Progres Permohonan Saya','progress'),*BACK]),reply(f'Nomor permohonan: {app.number}')]
            if app.duplicate_review: responses.append(reply('Data akan diperiksa petugas bila diperlukan. Pantau perkembangan melalui menu progres.'))
            responses.extend(dispatch(user,'','screen'))
            return responses
    if action=='confirm_cancel':
        RegistrationDraft.objects.filter(user=user,form_status='DRAFT_REGISTRASI').delete()
        set_state(user,mode='menu')
        return [reply('Draft dibatalkan. Registrasi resmi sebelumnya tetap tersimpan.',BACK)]
    if action=='screen':
        app=active_application(user)
        if not app: return [reply('Kirim registrasi terlebih dahulu sebelum mengisi Skrining.',[('Registrasi Pemohon','register'),*BACK])]
        if app.status not in (Status.WAIT_SCREEN,Status.NEED_INFO): return [reply('Skrining Anda sudah dikirim. Pantau tindak lanjut petugas.',[('Progres Permohonan Saya','progress'),*BACK])]
        saved=ScreeningDraft.objects.filter(application=app).first()
        if saved:
            set_state(user,mode='screening_review',application=str(app.pk))
            return [reply('Ringkasan Skrining tersimpan\n'+saved.text,[('Ubah','screen_edit'),('Kirim Skrining','screen_send'),*BACK])]
        set_state(user,mode='screening',application=str(app.pk))
        return [reply('💬 LANGKAH 2/3 · KENDALA\n\n'+SCREEN_PROMPT,[('Pengaturan Notifikasi','notify'),*BACK])]
    if action in ('screen_edit','screen_send'):
        app=active_application(user)
        if not app: raise ValidationError('Permohonan aktif tidak tersedia.')
        if action=='screen_edit':
            set_state(user,mode='screening',application=str(app.pk))
            return [reply('💬 LANGKAH 2/3 · KENDALA\n\n'+SCREEN_PROMPT,[('Pengaturan Notifikasi','notify'),*BACK])]
        saved=ScreeningDraft.objects.filter(application=app).first()
        submit_screening(user,app,saved.text if saved else '')
        ScreeningDraft.objects.filter(application=app).delete()
        set_state(user,mode='menu')
        return [reply('✅ Kendala Anda telah tersimpan. Lanjut ke langkah terakhir: Self Asesmen dan bukti pengisian.')] + dispatch(user,'','self')
    if action=='directory': return [reply('Pilih kategori titik akses.',[(label,f'category:{key}') for key,label in Category.choices if key!=Category.COORD])]
    if action.startswith('category:'): return [directory(action.split(':',1)[1])]
    if action=='self':
        app = active_application(user)
        if not app:
            return [reply('Mulai dengan mengisi data diri terlebih dahulu.', [('Registrasi Pemohon','register'),*BACK])]
        if not app.screenings.exists():
            return [reply('Sampaikan kendala Anda terlebih dahulu.', [('Skrining','screen'),*BACK])]
        if app.status not in (Status.WAIT_ASSESS,Status.WAIT_PROOF,Status.NEED_INFO):
            return [reply('📬 Berkas Anda sudah dikirim. Pantau proses verifikasinya.', [('Progres Permohonan Saya','progress'),*BACK])]
        if not site_config().self_assessment_url:
            return [reply('🌿 LANGKAH 3/3 · SELF ASESMEN\n\nData diri dan kendala tersimpan. Tautan BOSS BNN / Self Asesmen sedang disiapkan pengelola. Setelah tautan tersedia, kembali ke menu ini untuk mengisi dan mengirim bukti. Tidak ada skor atau hasil yang dibuat oleh bot.', [('Periksa tautan kembali','self'),*BACK])]
        app = begin_assessment(user,app)
        return [reply('🌿 LANGKAH 3/3 · SELF ASESMEN\n\n1. Buka tautan resmi di bawah.\n2. Isi Self Asesmen di website tersebut.\n3. Kembali ke bot dan kirim screenshot bukti pengisian.\n\nHasil ditampilkan oleh website penyedia. Screenshot adalah bukti kiriman Anda dan akan diverifikasi Pelaksana, bukan hasil terverifikasi otomatis.', [('Buka Self Asesmen / BOSS BNN','url:'+app.assessment_url),('Sudah mengisi · Kirim bukti','evidence_begin'),*BACK])]
    if action in ('evidence_begin','evidence_consent'):
        app = active_application(user)
        if not app or app.status not in (Status.WAIT_PROOF,Status.NEED_INFO) or not app.assessment_url:
            raise ValidationError('Buka tahap Self Asesmen terlebih dahulu.')
        if action=='evidence_begin':
            return [reply('🔒 Bukti hanya dapat dilihat petugas berwenang. Kirim screenshot secukupnya sebagai bukti pengisian; tutup informasi lain yang tidak diperlukan. Dengan melanjutkan Anda menyatakan telah mengisi dan setuju bukti disimpan untuk verifikasi layanan.', [('Saya setuju · Unggah screenshot','evidence_consent'),*BACK])]
        set_state(user,mode='evidence',application=str(app.pk))
        return [reply('📸 Silakan kirim screenshot sebagai Foto, bukan dokumen. Maksimal 5 MB. Bukti akan masuk ke berkas Anda untuk diverifikasi Pelaksana.',BACK)]
    if not action and photo is None and state.get('mode')=='evidence':
        return [reply('Kirim screenshot sebagai Foto melalui ikon lampiran Telegram, bukan teks atau dokumen.',BACK)]
    if photo is not None:
        if state.get('mode')!='evidence':
            return [reply('Buka Self Asesmen → Kirim bukti terlebih dahulu agar foto terhubung ke permohonan Anda.',[('Self Asesmen','self'),*BACK])]
        app = Application.objects.get(pk=state['application'],applicant__user=user,deleted_at__isnull=True)
        submit_evidence(user,app,photo)
        set_state(user,mode='menu')
        return [reply('🎉 BERKAS ANDA LENGKAP\n\n✅ Data diri\n✅ Skrining/kendala\n✅ Bukti pengisian Self Asesmen\n\nBerkas telah masuk ke antrean verifikasi Pelaksana. Notifikasi diantrekan; status pengirimannya tercatat di sistem.', [('Progres Permohonan Saya','progress'),('Pengaturan Notifikasi','notify'),*BACK])]

    if action=='progress':
        apps = Application.objects.filter(applicant__user=user,deleted_at__isnull=True).select_related('location').order_by('-submitted_at')
        if not apps.exists(): return [reply('Anda belum memiliki permohonan yang dikirim.',[('Registrasi Pemohon','register'),*BACK])]
        # History is selectable so long response lists do not exceed Telegram limits.
        return [reply('Pilih permohonan Anda.',[(a.number,f'my:{a.pk}') for a in apps[:30]]+ [('Pengaturan Notifikasi','notify'),*BACK])]
    if action.startswith('my:'):
        app=Application.objects.filter(pk=action.split(':')[1],applicant__user=user,deleted_at__isnull=True).select_related('location').first()
        if not app: raise PermissionDenied()
        return [reply(public_progress(user,app),[('Perbarui Progres',action),*BACK])]
    if action=='notify': return [reply('Notifikasi hanya berisi pemberitahuan umum tanpa NIK, uraian Skrining, atau catatan internal. Pilih persetujuan kanal.',[('Setuju Notifikasi Bot','notify_bot'),('Setuju & Kaitkan Akun Institusi','notify_link'),('Nonaktifkan Notifikasi','notify_off'),*BACK])]
    if action in ('notify_bot','notify_register','notify_skip','notify_admin'):
        user.bot_notifications = action != 'notify_skip'
        user.notification_decided = True
        user.notification_consent_at = timezone.now() if user.bot_notifications else None
        user.save(update_fields=['bot_notifications','notification_decided','notification_consent_at'])
        # Retry previously blocked consent failures only; never replay simulations.
        if user.bot_notifications:
            Notification.objects.filter(recipient=user,status='failed',error='recipient_not_consented',attempts__lt=5).update(next_attempt_at=timezone.now())
        if action in ('notify_register','notify_skip'):
            return dispatch(user,'','register')
        if action=='notify_admin':
            return dispatch(user,'','admin')
        return [reply('🔔 Persetujuan notifikasi bot dicatat. Pemberitahuan dikirim otomatis ketika bot dan pekerjanya berjalan dalam mode live.',BACK)]
    if action=='notify_link':
        raw=create_recipient_link(user)
        return [reply(f'Kirim /kaitkan {raw} melalui percakapan pribadi ke akun institusi resmi yang diberikan pengelola. Berlaku 10 menit dan sekali pakai. Pengiriman hanya aktif setelah identitas pengirim terverifikasi.',BACK)]
    if action=='notify_off':
        user.bot_notifications=False; user.save(update_fields=['bot_notifications'])
        NotificationRecipient.objects.filter(user=user).update(active=False)
        RecipientLink.objects.filter(user=user,used_at__isnull=True).update(expires_at=timezone.now())
        return [reply('Persetujuan notifikasi dicabut.',BACK)]
    if action=='admin':
        officer=user_officer(user)
        if officer_active(officer):
            set_state(user,mode='menu')
            return [reply('🧑‍💼 '+officer.get_role_display()+' · SALAM MANIS\n\nBerkas lengkap masuk otomatis ke antrean verifikasi. Pilih tindakan Anda.',ADMIN+[('Pengaturan Notifikasi','notify')])]
        set_state(user,mode='activation')
        return [reply('Silakan masukkan kode akses admin yang diberikan oleh pengelola SALAM MANIS.',[('Kembali ke Menu Awal','home')])]
    if action.startswith('admin_') or action=='dashboard':
        officer=user_officer(user)
        if not officer_active(officer): raise PermissionDenied()
        cases=cases_for(officer)
        if action=='admin_profile':
            return [reply('\n'.join(f'{officer.get_role_display()} — {x.location.name}' for x in assignments(officer).select_related('location')),[('Pengaturan Notifikasi','notify'),('Menu Admin','admin')])]
        if action=='dashboard': return [reply(f'Login dashboard terpisah diperlukan. {settings.DASHBOARD_URL or "Alamat dashboard belum dikonfigurasi pengelola."}',[('Menu Admin','admin')])]
        if action=='admin_summary':
            return [reply('\n'.join(f'{label}: {cases.filter(status=key).count()}' for key,label in Status.choices),[('Menu Admin','admin')])]
        if action in ('admin_list','admin_pending','admin_update'):
            if action=='admin_pending': cases=cases.exclude(status__in=CLOSED)
            page=0
            return [admin_page(cases,page,action)]
        if action.startswith('admin_page:'):
            _,kind,page=action.split(':')
            if kind=='pending': cases=cases.exclude(status__in=CLOSED)
            return [admin_page(cases,int(page),'admin_'+kind)]
        if action.startswith('admin_proof:'):
            app=cases.filter(pk=action.split(':')[1]).first()
            if not app: raise PermissionDenied()
            item=app.evidence.order_by('-submitted_at','-pk').first()
            if not item: raise ValidationError('Bukti belum tersedia.')
            audit(f'officer:{officer.pk}','evidence.viewed_in_bot',item.pk)
            result=reply('📸 Bukti pengisian Self Asesmen — kiriman pemohon/petugas. Periksa kesesuaiannya sebelum memverifikasi.', [('Kembali ke berkas',f'admin_case:{app.pk}')])
            result['evidence_id']=item.pk
            return [result]
        if action.startswith('admin_verify:') or action.startswith('admin_reject:'):
            app=cases.filter(pk=action.split(':')[1]).first()
            if not app or app.status!=Status.WAIT_VERIFY: raise PermissionDenied()
            set_state(user,mode='verification',application=str(app.pk),accepted=action.startswith('admin_verify:'))
            return [reply('Isi catatan verifikasi. Hasil yang diterima adalah bukti pengisian, bukan keputusan klinis. Untuk meminta kelengkapan, jelaskan perbaikannya tanpa informasi sensitif.', [('Menu Admin','admin')])]
        if action.startswith('admin_case:'):

            app=cases.filter(pk=action.split(':')[1]).first()
            if not app: raise PermissionDenied()
            latest = app.screenings.order_by('-version').first()
            evidence = app.evidence.order_by('-submitted_at','-pk').first()
            buttons=[]
            if evidence: buttons.append(('📸 Lihat bukti screenshot',f'admin_proof:{app.pk}'))
            if app.status==Status.WAIT_VERIFY and evidence:
                buttons += [('✅ Berkas sesuai',f'admin_verify:{app.pk}'),('📝 Minta perbaikan',f'admin_reject:{app.pk}')]
            buttons += [(Status(st).label,f'admin_status:{app.pk}:{Status.values.index(st)}') for st in sorted(TRANSITIONS[app.status]) if st!=Status.REVIEW or app.legacy_submission]
            buttons += [('Buka Dashboard','dashboard'),('Menu Admin','admin')]
            return [reply(f'📂 {app.number}\nStatus: {app.get_status_display()}\n\n'+masked(app.identity)+'\n\n💬 Kendala:\n'+(latest.text if latest else 'Belum diisi')+'\n\n📸 Bukti Self Asesmen: '+('Ada — buka detail dashboard untuk melihat screenshot privat.' if evidence else 'Belum dikirim'),buttons)]
        if action.startswith('admin_status:'):
            _,pk,status=action.split(':')
            status=Status.values[int(status)]
            app=cases.filter(pk=pk).first()
            if not app or status not in TRANSITIONS[app.status]: raise PermissionDenied()
            set_state(user,mode='admin_reason',application=str(app.pk),status=status,expected=app.status)
            return [reply('Isi alasan internal perubahan status. Pesan publik diisi pada langkah berikutnya.',[('Menu Admin','admin')])]
    if not action and text:
        if state.get('mode')=='evidence':
            return [reply('Kirim screenshot sebagai Foto melalui ikon lampiran Telegram, bukan teks atau dokumen.',BACK)]
        if state.get('mode')=='verification':
            officer=user_officer(user)
            app=cases_for(officer).filter(pk=state['application']).first()
            if not app: raise PermissionDenied()
            verify_application(officer,app,state['accepted'],text, '' if state['accepted'] else text)
            set_state(user,mode='menu')
            return [reply('✅ Verifikasi disimpan. Pemberitahuan pemohon masuk antrean otomatis.',ADMIN)]
        if state.get('mode')=='activation':
            if activate(user,text):
                set_state(user,mode='menu')
                return [reply('✅ Aktivasi berhasil. Aktifkan pemberitahuan agar berkas baru cepat Anda ketahui.', [('🔔 Setuju notifikasi & buka menu','notify_admin'),('Menu Admin','admin')])]
            return [reply('Kode tidak dapat digunakan. Coba kembali nanti atau kembali ke menu awal.',[('Coba Kembali','admin'),('Kembali ke Menu Awal','home')])]
        if state.get('mode')=='registration':
            draft=RegistrationDraft.objects.get(user=user,form_status='DRAFT_REGISTRASI')
            if draft.step>=len(FIELDS): return [summary(draft)]
            key=FIELDS[draft.step][0]
            draft.data[key]=validate_field(key,text)
            if draft.editing:
                draft.step=next((i for i,(k,_) in enumerate(FIELDS) if not draft.data.get(k)),len(FIELDS)); draft.editing=False
            else: draft.step+=1
            draft.save()
            return [summary(draft) if draft.step>=len(FIELDS) else draft_prompt(draft)]
        if state.get('mode')=='screening':
            if not text.strip() or len(text)>12000: raise ValidationError('Uraian wajib diisi, maksimal 12.000 karakter.')
            app=Application.objects.get(pk=state['application'],applicant__user=user)
            if app.status not in (Status.WAIT_SCREEN,Status.NEED_INFO): raise ValidationError('Tahap Skrining tidak tersedia.')
            ScreeningDraft.objects.update_or_create(application=app,defaults={'text':text.strip()})
            set_state(user,mode='screening_review',application=state['application'])
            return [reply('Ringkasan Skrining\n'+text.strip(),[('Ubah','screen_edit'),('Kirim Skrining','screen_send'),*BACK])]
        if state.get('mode') in ('admin_reason','admin_public'):
            officer=user_officer(user)
            app=cases_for(officer).filter(pk=state['application']).first()
            if not app: raise PermissionDenied()
            if not text.strip(): raise ValidationError('Isian wajib diisi.')
            if state['mode']=='admin_reason':
                set_state(user,mode='admin_public',application=state['application'],status=state['status'],expected=state['expected'],reason=text.strip())
                return [reply('Isi keterangan yang boleh dilihat pemohon, atau kirim tanda - jika tidak ada.',[('Menu Admin','admin')])]
            update_progress(officer,app,state['status'],state['reason'],'' if text.strip()=='-' else text.strip(),expected_status=state['expected'])
            set_state(user,mode='menu')
            return [reply('Progres disimpan dan notifikasi masuk antrean.',ADMIN)]
    return [reply('Silakan pilih menu. Draft tersimpan tetap tersedia.',[('Masyarakat','public'),('Admin','admin')])]

def admin_page(cases, page, action):
    page=max(0,page)
    items=list(cases.order_by('-submitted_at')[page*8:page*8+9])
    buttons=[(a.number,f'admin_case:{a.pk}') for a in items[:8]]
    kind=action.replace('admin_','')
    if page: buttons.append(('Sebelumnya',f'admin_page:{kind}:{page-1}'))
    if len(items)>8: buttons.append(('Selanjutnya',f'admin_page:{kind}:{page+1}'))
    buttons.append(('Menu Admin','admin'))
    return reply('Pilih permohonan sesuai hak akses.' if items else 'Tidak ada permohonan pada halaman ini.',buttons)
