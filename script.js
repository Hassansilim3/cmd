// Initialize Telegram Web App
let tg = window.Telegram.WebApp;
tg.expand();
tg.enableClosingConfirmation();

// User data
let userData = {
    id: tg.initDataUnsafe?.user?.id || 123456,
    username: tg.initDataUnsafe?.user?.username || 'TestUser',
    balance: 0,
    invites: 0,
    adsWatchedToday: 0,
    level: 1,
    points: 0,
    isAdmin: false,
    isSubscribed: false
};

// APIs base URL
const API_BASE = 'https://cmd-pearl.vercel.app/api';

// تحميل الإعدادات
async function loadSettings() {
    try {
        const resp = await fetch('/settings');
        const settings = await resp.json();
        window.appSettings = settings || {};
        window.appSettings.MIN_WITHDRAWAL = parseFloat(window.appSettings.MIN_WITHDRAWAL) || 15;
        console.log('App settings loaded:', window.appSettings);
    } catch (err) {
        console.error('Error loading settings.json:', err);
        window.appSettings = { MIN_WITHDRAWAL: 15 };
    }
}

// المتغيرات العامة
let currentWithdrawMethod = '';
let currentAdminAction = '';

// Initialize app
document.addEventListener('DOMContentLoaded', async function() {
    console.log("App initialized");
    await loadSettings();
    loadUserData();
    updateDisplay();
    generateInviteLink();
    initComboGame(); // تهيئة اللعبة

    // Handle referral from URL
    const urlParams = new URLSearchParams(window.location.search);
    const referralId = urlParams.get('ref');
    if (referralId && referralId !== userData.id.toString()) {
        processReferral(referralId);
    }
});

// Load user data from API
// Load user data from API
async function loadUserData() {
    try {
        console.log("Loading user data for ID:", userData.id);
        const response = await fetch(`${API_BASE}/user-data`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ userId: userData.id })
        });

        console.log("Response status:", response.status);
        const data = await response.json();
        console.log("Response data:", data);

        if (data.success) {
            // ✅ تحديث كافة بيانات المستخدم من الخادم
            userData = { 
                ...userData, 
                ...data.user,
                balance: data.user.balance // ✅ التأكد من تحديث الرصيد من الخادم
            };
            updateDisplay();

            if (userData.isSubscribed === false) {
                showPage('channels');
                showMessage('يجب الاشتراك في القنوات لاستخدام التطبيق', 'error');
                document.getElementById('BottomNavigation').style['display'] = 'none';
                return;
            }
        } else {
            console.error('Server error:', data.error);
            showMessage('خطأ في تحميل البيانات: ' + data.error, 'error');
        }
    } catch (err) {
        console.error('Error loading user data:', err);
        showMessage('خطأ في الاتصال بالخادم', 'error');
    }
}

// Save user data
async function saveUserData() {
    try {
        await fetch(`${API_BASE}/update-user`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userData)
        });
    } catch (err) {
        console.error('Error updating user data:', err);
    }
}

// ✅ دالة جديدة: تحميل وعرض القنوات الإجبارية من settings.json
async function loadChannels() {
    try {
        const response = await fetch('/settings');
        const settings = await response.json();
        const channels = settings.REQUIRED_CHANNELS || [];
        const container = document.getElementById('channelsList');
        container.innerHTML = '';

        channels.forEach((channel, index) => {
            const channelId = `channel-${index + 1}`;
            const statusId = `status-${index + 1}`;

            const channelHTML = `
                <div class="task-item" id="${channelId}">
                    <div class="task-header">
                        <div class="task-title"><i class="fas fa-hashtag"></i> ${channel.title}</div>
                        <div class="task-reward"><span id="${statusId}">غير مشترك</span></div>
                    </div>
                    <div class="task-description">
                        ${channel.description}
                    </div>
                    <button class="btn btn-primary" onclick="joinChannel('${channel.url}', '${channelId}', '${statusId}')">
                        <i class="fas fa-external-link-alt"></i> الذهاب إلى القناة
                    </button>
                </div>
            `;
            container.innerHTML += channelHTML;
        });
    } catch (err) {
        console.error('Error loading channels:', err);
        document.getElementById('channelsList').innerHTML = '<div class="error-message">❌ حدث خطأ في تحميل القنوات</div>';
    }
}

// Process referral
async function processReferral(referralId) {
    if (localStorage.getItem('ref_processed_' + referralId) === 'true') {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/process-referral`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userId: userData.id,
                referralId: referralId
            })
        });

        const data = await response.json();

        if (data.success) {
            userData.balance += 3;
            userData.invites += 1;
            saveUserData();
            updateDisplay();
            localStorage.setItem('ref_processed_' + referralId, 'true');
            showMessage('تمت إضافة 3 CMD لدعوة صديق!', 'success');
        }
    } catch (err) {
        console.error('Error processing referral:', err);
    }
}

// Update UI elements
function updateDisplay() {
    document.getElementById('userBalance').textContent = userData.balance.toFixed(2) + ' CMD';
    document.getElementById('inviteCount').textContent = userData.invites;
    document.getElementById('adsToday').textContent = userData.adsWatchedToday + '/50';
    document.getElementById('userLevel').textContent = userData.level;
    document.getElementById('userPoints').textContent = userData.points;
    document.getElementById('withdrawBalance').textContent = userData.balance.toFixed(2) + ' CMD';
    document.getElementById('totalInvites').textContent = userData.invites;
    
    const adsProgress = (userData.adsWatchedToday / 50) * 100;
    document.getElementById('adsProgress').style.width = adsProgress + '%';
    document.getElementById('adsProgressText').textContent = userData.adsWatchedToday + '/50 إعلان';

    const minWithdrawal = parseFloat(window.appSettings?.MIN_WITHDRAWAL ?? 15);

    const homeMinEl = document.getElementById('homeMinWithdrawText');
    if (homeMinEl) {
        homeMinEl.textContent = `1 CMD = 0.005 USDT | يمكنك السحب عند الوصول إلى ${minWithdrawal} CMD`;
    }

    const withdrawMinEl = document.getElementById('withdrawMinWithdrawText');
    if (withdrawMinEl) {
        withdrawMinEl.textContent = `الحد الأدنى للسحب هو ${minWithdrawal} CMD (${(minWithdrawal * 0.005).toFixed(2)} USDT)`;
    }

    const infoMinEl = document.getElementById('infoMinWithdrawText');
    if (infoMinEl) {
        infoMinEl.textContent = `سحب الأرباح: عند الوصول إلى ${minWithdrawal} CMD`;
    }

    const withdrawAmountInput = document.getElementById('withdrawAmount');
    if (withdrawAmountInput) {
        withdrawAmountInput.min = minWithdrawal;
        withdrawAmountInput.placeholder = `أدخل المبلغ (الحد الأدنى ${minWithdrawal} CMD)`;
        const amount = parseFloat(withdrawAmountInput.value) || 0;
        const usdtAmount = amount * 0.005;
        document.getElementById('usdtEquivalent').textContent = usdtAmount.toFixed(2) + ' USDT';
    }
}

// Generate invite link
function generateInviteLink() {
    const link = `https://t.me/cryptoworldxbot?start=ref${userData.id}`;
    document.getElementById('inviteLink').textContent = link;
}

// Copy invite link
function copyInviteLink() {
    const link = document.getElementById('inviteLink').textContent;
    navigator.clipboard.writeText(link).then(() => {
        showMessage('تم نسخ الرابط بنجاح!', 'success');
    }).catch(err => {
        showMessage('فشل في نسخ الرابط', 'error');
        console.error('Failed to copy:', err);
    });
}

// Select withdraw method
function selectWithdrawMethod(method) {
    currentWithdrawMethod = method;
    document.querySelectorAll('.withdraw-method').forEach(item => {
        item.classList.remove('selected');
    });
    document.querySelector(`.withdraw-method[data-method="${method}"]`).classList.add('selected');

    const label = document.getElementById('withdrawDetailsLabel');
    const input = document.getElementById('withdrawAddress');

    switch(method) {
        case 'vodafone':
            label.textContent = 'رقم فودافون كاش';
            input.placeholder = 'أدخل رقم فودافون كاش';
            break;
        case 'orange':
            label.textContent = 'رقم أورانج كاش';
            input.placeholder = 'أدخل رقم أورانج كاش';
            break;
        case 'egmoney':
            label.textContent = 'رقم EG Money';
            input.placeholder = 'أدخل رقم EG Money';
            break;
        case 'binance':
            label.textContent = 'Binance ID';
            input.placeholder = 'أدخل Binance ID';
            break;
        case 'bybit':
            label.textContent = 'Bybit ID';
            input.placeholder = 'أدخل Bybit ID';
            break;
        case 'okx':
            label.textContent = 'OKX ID';
            input.placeholder = 'أدخل OKX ID';
            break;
        case 'ton':
            label.textContent = 'عنوان محفظة TON';
            input.placeholder = 'أدخل عنوان محفظة TON';
            break;
        case 'usdt':
            label.textContent = 'عنوان محفظة USDT';
            input.placeholder = 'أدخل عنوان محفظة USDT';
            break;
       case 'userrrr':
            label.textContent = 'رابط القناة 👇';
            input.placeholder = 'رابط القناة';
            break;
    }
}

// Process withdrawal
async function processWithdrawal() {
    if (!currentWithdrawMethod) {
        showMessage('يرجى اختيار طريقة السحب', 'error');
        return;
    }

    const address = document.getElementById('withdrawAddress').value;
    const amount = parseFloat(document.getElementById('withdrawAmount').value);

    if (!address) {
        showMessage('يرجى إدخال عنوان المحفظة', 'error');
        return;
    }

    const min = parseFloat(window.appSettings?.MIN_WITHDRAWAL ?? 15);

    if (!amount || amount < min) {
        showMessage(`الحد الأدنى للسحب هو ${min} CMD`, 'error');
        return;
    }

    if (amount > userData.balance) {
        showMessage('رصيدك غير كافي للسحب', 'error');
        return;
    }

    showMessage('جاري معالجة طلب السحب...', 'info');

    try {
        const response = await fetch(`${API_BASE}/withdraw`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userId: userData.id,
                amount: amount,
                method: currentWithdrawMethod,
                address: address
            })
        });

        const data = await response.json();

        if (data.success) {
            userData.balance -= amount;
            updateDisplay();
            saveUserData();
            showMessage('تم إرسال طلب السحب بنجاح! سيتم معالجته خلال 24 ساعة', 'success');

            document.getElementById('withdrawAddress').value = '';
            document.getElementById('withdrawAmount').value = '';
            currentWithdrawMethod = '';

            document.querySelectorAll('.withdraw-method').forEach(item => {
                item.classList.remove('selected');
            });
        } else {
            showMessage(data.error, 'error');
        }
    } catch (err) {
        console.error('Error processing withdrawal:', err);
        showMessage('حدث خطأ أثناء معالجة طلب السحب', 'error');
    }
}

// Submit partnership request
async function submitPartnershipRequest() {
    const channelName = document.getElementById('channelName').value;
    const channelLink = document.getElementById('channelLink').value;
    const channelDescription = document.getElementById('channelDescription').value;

    if (!channelName || !channelLink) {
        showMessage('يرجى ملء جميع الحقول المطلوبة', 'error');
        return;
    }

    showMessage('جاري إرسال طلب الشراكة...', 'info');

    try {
        const response = await fetch(`${API_BASE}/partnership-request`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userData.id,
                channel_name: channelName,
                channel_link: channelLink,
                channel_description: channelDescription
            })
        });

        const data = await response.json();

        if (data.success) {
            showMessage('تم إرسال طلب الشراكة بنجاح! سيتم الرد عليك قريباً', 'success');
            document.getElementById('channelName').value = '';
            document.getElementById('channelLink').value = '';
            document.getElementById('channelDescription').value = '';
            closeModal('partnershipModal');
        } else {
            showMessage(data.error, 'error');
        }
    } catch (err) {
        console.error('Error submitting partnership request:', err);
        showMessage('حدث خطأ أثناء إرسال طلب الشراكة', 'error');
    }
}

// Load all users
async function loadAllUsers() {
    try {
        const response = await fetch(`${API_BASE}/admin/users?admin_id=${userData.id}`);
        const data = await response.json();

        if (data.success) {
            let html = '<div class="info-box"><h3>جميع المستخدمين</h3>';
            data.users.forEach(user => {
                html += `
                    <div class="user-info">
                        <p><strong>ID:</strong> ${user.id}</p>
                        <p><strong>اسم المستخدم:</strong> ${user.username || 'غير متوفر'}</p>
                        <p><strong>الاسم:</strong> ${user.first_name || 'غير متوفر'}</p>
                        <p><strong>الرصيد:</strong> ${user.balance} CMD</p>
                        <p><strong>المدعوون:</strong> ${user.invites}</p>
                        <p><strong>المستوى:</strong> ${user.level}</p>
                        <p><strong>النقاط:</strong> ${user.points}</p>
                        <p><strong>الحالة:</strong> ${user.banned ? 'محظور' : 'نشط'}</p>
                        <hr>
                    </div>
                `;
            });
            html += '</div>';
            document.getElementById('usersList').innerHTML = html;
        } else {
            showMessage(data.error, 'error');
        }
    } catch (err) {
        console.error('Error loading users:', err);
        showMessage('حدث خطأ أثناء تحميل المستخدمين', 'error');
    }
}

// Search user
async function searchUser() {
    const userId = document.getElementById('searchUserId').value;

    if (!userId) {
        showMessage('يرجى إدخال معرف المستخدم', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/admin/user-info`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                admin_id: userData.id,
                user_id: userId
            })
        });

        const data = await response.json();

        if (data.success) {
            const user = data.user;
            const html = `
                <div class="info-box">
                    <h3>معلومات المستخدم</h3>
                    <p><strong>ID:</strong> ${user.id}</p>
                    <p><strong>اسم المستخدم:</strong> ${user.username || 'غير متوفر'}</p>
                    <p><strong>الاسم:</strong> ${user.first_name || 'غير متوفر'} ${user.last_name || ''}</p>
                    <p><strong>الرصيد:</strong> ${user.balance} CMD</p>
                    <p><strong>المدعوون:</strong> ${user.invites}</p>
                    <p><strong>الإعلانات اليوم:</strong> ${user.ads_watched_today}/50</p>
                    <p><strong>المستوى:</strong> ${user.level}</p>
                    <p><strong>النقاط:</strong> ${user.points}</p>
                    <p><strong>الحالة:</strong> ${user.banned ? 'محظور' : 'نشط'}</p>
                    <p><strong>آخر مشاهدة إعلان:</strong> ${user.last_ad_watch || 'لم يشاهد بعد'}</p>
                    <p><strong>تاريخ الإنشاء:</strong> ${user.created_at}</p>
                </div>
            `;
            document.getElementById('searchResult').innerHTML = html;
        } else {
            showMessage(data.error, 'error');
        }
    } catch (err) {
        console.error('Error searching user:', err);
        showMessage('حدث خطأ أثناء البحث عن المستخدم', 'error');
    }
}

// Load stats
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/admin/stats?admin_id=${userData.id}`);
        const data = await response.json();

        if (data.success) {
            const stats = data.stats;
            const html = `
                <div class="info-box">
                    <h3>إحصائيات النظام</h3>
                    <p><strong>إجمالي المستخدمين:</strong> ${stats.total_users}</p>
                    <p><strong>المستخدمين النشطين اليوم:</strong> ${stats.active_today}</p>
                    <p><strong>إجمالي المدعوين:</strong> ${stats.total_invites}</p>
                    <p><strong>إجمالي عمليات السحب:</strong> ${stats.total_withdrawals} CMD</p>
                    <p><strong>الإعلانات اليوم:</strong> ${stats.today_ads}</p>
                    <p><strong>المسجلين اليوم:</strong> ${stats.today_signups}</p>
                    <p><strong>إجمالي الرصيد:</strong> ${stats.total_balance} CMD</p>
                </div>
            `;
            document.getElementById('statsResult').innerHTML = html;
        } else {
            showMessage(data.error, 'error');
        }
    } catch (err) {
        console.error('Error loading stats:', err);
        showMessage('حدث خطأ أثناء تحميل الإحصائيات', 'error');
    }
}

// Load leaderboard with top 3 and full list
async function loadLeaderboard() {
    const topThreeContainer = document.getElementById('topThree');
    const container = document.getElementById('leaderboardList');

    topThreeContainer.innerHTML = '<div style="text-align: center; color: var(--light-text); padding: 20px;">جاري تحميل المتصدرين...</div>';
    container.innerHTML = '';

    try {
        const response = await fetch(`${API_BASE}/leaderboard`);
        const data = await response.json();

        topThreeContainer.innerHTML = '';
        container.innerHTML = '';

        if (data.leaderboard && data.leaderboard.length > 0) {
            const topThree = data.leaderboard.slice(0, 3);
            topThree.forEach((user, index) => {
                const topUserDiv = document.createElement('div');
                topUserDiv.className = `top-user top-user-${index + 1}`;
                const avatarText = user.first_name ? user.first_name.charAt(0) : user.username ? user.username.charAt(0) : 'U';

                topUserDiv.innerHTML = `
                    <div class="top-user-avatar">
                        <img src="https://t.me/i/userpic/320/${user.username || 'default'}.jpg"
                             onerror="this.src='https://t.me/i/userpic/320/default.jpg'; this.style.backgroundColor='var(--accent)'; this.style.display='flex'; this.style.alignItems='center'; this.style.justifyContent='center'; this.textContent='${avatarText}'; this.style.fontWeight='bold'; this.style.color='white';"
                             style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">
                    </div>
                    <div class="top-user-name">${user.first_name || user.username || 'مستخدم'}</div>
                    <div class="top-user-points">
                        ${index === 0 ? '<i class="fas fa-crown crown-icon"></i>' : ''}
                        ${user.balance.toFixed(2)}
                        <span style="color: var(--gold);">CMD</span>
                    </div>
                `;
                topThreeContainer.appendChild(topUserDiv);
            });

            data.leaderboard.slice(3).forEach((user, index) => {
                const item = document.createElement('div');
                item.className = 'leaderboard-item';
                const avatarText = user.first_name ? user.first_name.charAt(0) : user.username ? user.username.charAt(0) : 'U';

                item.innerHTML = `
                    <div class="rank">#${index + 4}</div>
                    <div class="user-avatar">
                        <img src="https://t.me/i/userpic/320/${user.username || 'default'}.jpg"
                             onerror="this.src='https://t.me/i/userpic/320/default.jpg'; this.style.backgroundColor='var(--accent)'; this.style.display='flex'; this.style.alignItems='center'; this.style.justifyContent='center'; this.textContent='${avatarText}'; this.style.fontWeight='bold'; this.style.color='white';"
                             style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">
                    </div>
                    <div class="user-info">
                        <div class="username">${user.first_name || user.username || 'مستخدم'}</div>
                        <div class="user-points">
                            ${user.balance.toFixed(2)}
                            <span style="color: var(--gold);">CMD</span>
                        </div>
                    </div>
                `;
                container.appendChild(item);
            });
        } else {
            topThreeContainer.innerHTML = '';
            container.innerHTML = '<div style="text-align: center; color: var(--light-text); padding: 20px;">لا توجد مستخدمين في المتصدرين حالياً<br>كن أول من يجمع النقاط!</div>';
        }
    } catch (err) {
        console.error('Error loading leaderboard:', err);
        topThreeContainer.innerHTML = '';
        container.innerHTML = `
            <div style="text-align: center; color: var(--light-text); padding: 20px;">
                <div>خطأ في الاتصال بالخادم</div>
                <button onclick="loadLeaderboard()" style="margin-top: 10px; padding: 8px 16px; background: var(--info); color: white; border: none; border-radius: 8px; cursor: pointer;">
                    إعادة المحاولة
                </button>
            </div>
        `;
    }
}

// Show message
function showMessage(text, type) {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-icon">
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        </div>
        <div class="notification-content">${text}</div>
        <button class="notification-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    document.body.appendChild(notification);
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

// ✅ دالة جديدة: تحميل وعرض قائمة الإحالات
async function loadReferrals() {
    const container = document.getElementById('referralsList');
    container.innerHTML = '<div style="text-align: center; color: var(--light-text); padding: 20px;">جارٍ تحميل قائمة الإحالات...</div>';
    try {
        const response = await fetch(`${API_BASE}/get_referrals?user_id=${userData.id}`);
        const data = await response.json();
        if (data.success) {
            if (data.referrals.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: var(--light-text); padding: 20px;">لا توجد إحالات حتى الآن. شارك رابطك لبدء كسب المكافآت!</div>';
                return;
            }
            let html = '<ul style="list-style: none; padding: 0; margin: 0;">';
            data.referrals.forEach(referral => {
                html += `
                    <li style="padding: 12px 0; border-bottom: 1px solid var(--card-border-light); display: flex; justify-content: space-between; align-items: center;">
                        <span><strong>ID:</strong> ${referral.id} | <strong>Username:</strong> ${referral.username || '---'}</span>
                        <span style="color: var(--gold); font-weight: bold;">+3 CMD</span>
                    </li>
                `;
            });
            html += '</ul>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<div style="text-align: center; color: var(--error); padding: 20px;">❌ ' + (data.error || 'حدث خطأ أثناء تحميل الإحالات') + '</div>';
        }
    } catch (err) {
        container.innerHTML = '<div style="text-align: center; color: var(--error); padding: 20px;">❌ حدث خطأ في الاتصال بالخادم.</div>';
        console.error('Error loading referrals:', err);
    }
}

// Page navigation
function showPage(pageId) {
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    document.getElementById(pageId).classList.add('active');
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    const navItems = document.querySelectorAll('.nav-item');
    const pageIndex = ['home', 'tasks', 'invite', 'withdraw', 'leaderboard', 'games'].indexOf(pageId);
    if (pageIndex !== -1 && navItems[pageIndex]) {
        navItems[pageIndex].classList.add('active');
    }

    if (pageId === 'leaderboard') {
        loadLeaderboard();
    }
    if (pageId === 'tasks') {
        loadTasks();
    }
    if (pageId === 'withdraw') {
        document.getElementById('withdrawAmount').addEventListener('input', function() {
            const amount = parseFloat(this.value) || 0;
            const usdtAmount = amount * 0.005;
            document.getElementById('usdtEquivalent').textContent = usdtAmount.toFixed(2) + ' USDT';
        });
        loadPaymentMethods();
    }
    if (pageId === 'channels') {
        loadChannels();
    }
    if (pageId === 'invite') {
        loadReferrals();
    }
    if (pageId === 'games') {
        updateComboGameButton();
    }
}

// ✅ دالة جديدة: تحميل وعرض المهام
async function loadTasks() {
    const container = document.getElementById('tasksContainer');
    container.innerHTML = '<div class="loading-message">جاري تحميل المهام...</div>';

    try {
        const response = await fetch(`${API_BASE}/tasks?user_id=${userData.id}`);
        const data = await response.json();

        if (data.success) {
            if (data.tasks.length === 0) {
                container.innerHTML = '<div class="no-tasks">🎉 مبروك! لقد أكملت جميع المهام المتاحة حاليًا. عد لاحقًا لمزيد من المهام.</div>';
                return;
            }

            let tasksHTML = '';
            data.tasks.forEach(task => {
                tasksHTML += `
                    <div class="task-card">
                        <div class="task-header">
                            <div class="task-title">
                                <i class="fas fa-tasks"></i>
                                ${task.title}
                            </div>
                            <div class="task-reward">
                                <i class="fas fa-coins"></i>
                                ${task.reward} CMD
                            </div>
                        </div>
                        <div class="task-description">
                            ${task.description || 'لا يوجد وصف لهذه المهمة.'}
                        </div>
                        <div class="task-actions">
                            <button class="btn-task btn-join" onclick="window.open('${task.channel}', '_blank')">
                                <i class="fas fa-external-link-alt"></i>
                                الإنتقال
                            </button>
                            <button class="btn-task btn-complete" onclick="completeTask(${task.id})">
                                <i class="fas fa-check-circle"></i>
                                تأكيد الإكمال
                            </button>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = tasksHTML;
        } else {
            container.innerHTML = '<div class="no-tasks">❌ حدث خطأ أثناء تحميل المهام. يرجى المحاولة لاحقًا.</div>';
            console.error('Error loading tasks:', data.error);
        }
    } catch (err) {
        container.innerHTML = '<div class="no-tasks">❌ حدث خطأ في الاتصال بالخادم.</div>';
        console.error('Network error loading tasks:', err);
    }
}

// ✅ دالة جديدة: تحميل وعرض وسائل الدفع من settings.json
async function loadPaymentMethods() {
    try {
        let settings = window.appSettings;
        if (!settings) {
            const response = await fetch('/settings');
            settings = await response.json();
            window.appSettings = settings;
        }
        const container = document.getElementById('withdrawMethods');
        let html = '';
        const methodsByCategory = { digital: [], exchange: [], local: [] };
        (settings.PAYMENT_METHODS || []).forEach(method => {
            methodsByCategory[method.category].push(method);
        });
        const categoryTitles = { digital: 'المحافظ الرقمية', exchange: 'منصات التداول', local: 'المحافظ المحلية' };
        Object.keys(methodsByCategory).forEach(category => {
            if (methodsByCategory[category].length > 0) {
                html += `<div style="grid-column: 1 / -1; text-align: right; font-weight: bold; color: var(--gold); margin: 15px 0 5px;">${categoryTitles[category]}</div>`;
                methodsByCategory[category].forEach(method => {
                    const isImageUrl = /\.(png|jpg|jpeg|webp|gif|svg)$/i.test(method.icon);
                    const iconHtml = isImageUrl
                        ? `<img src="${method.icon}" style="height: 42px; object-fit: contain; border-radius: 4px;" onerror="this.style.display='none';">`
                        : `<i class="${method.icon}"></i>`;
                    html += `
                        <div class="withdraw-method" data-method="${method.id}" onclick="selectWithdrawMethod('${method.id}')">
                            <div class="withdraw-method-icon">${iconHtml}</div>
                            <div class="withdraw-method-name">${method.name}</div>
                        </div>
                    `;
                });
            }
        });
        container.innerHTML = html;
    } catch (err) {
        console.error('Error loading payment methods:', err);
        document.getElementById('withdrawMethods').innerHTML = '<div style="text-align: center; color: var(--error); padding: 20px;">❌ حدث خطأ في تحميل وسائل الدفع</div>';
    }
}

// ✅ دالة جديدة: تأكيد إكمال مهمة
async function completeTask(taskId) {
    showMessage('جارٍ التحقق من إكمال المهمة...', 'info');

    try {
        const response = await fetch(`${API_BASE}/tasks/complete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userData.id,
                task_id: taskId
            })
        });

        const data = await response.json();

        if (data.success) {
            userData.balance += data.reward;
            updateDisplay();
            saveUserData();
            showMessage(`✅ تم إكمال المهمة بنجاح! حصلت على ${data.reward} CMD`, 'success');
            loadTasks();
        } else {
            showMessage(`❌ ${data.error}`, 'error');
        }
    } catch (err) {
        showMessage('❌ حدث خطأ أثناء معالجة طلبك. يرجى المحاولة لاحقًا.', 'error');
        console.error('Error completing task:', err);
    }
}

function finalVerification() {
    fetch('/api/verify-subscription', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId: window.Telegram.WebApp.initDataUnsafe.user.id })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('تم التحقق من اشتراكك! جاري تحميل التطبيق...', 'success');
            setTimeout(() => {
                location.reload();
            }, 2000);
        } else {
            showToast('فشل التحقق. تأكد من الاشتراك في جميع القنوات.', 'error');
        }
    });
}

// ✅ دالة للانتقال إلى القناة في تبويب جديد
function joinChannel(url, channelId, statusId) {
    window.open(url, '_blank');
}

// ✅ وظيفة للتحقق من الاشتراك
async function verifySubscription(channelId, statusId, channelUrl) {
    try {
        const response = await fetch(`${API_BASE}/verify-channel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userId: userData.id,
                channelUrl: channelUrl
            })
        });
        const data = await response.json();
        if (data.success) {
            document.getElementById(statusId).textContent = 'تم التحقق';
            document.getElementById(statusId).style.color = '#48bb78';
            document.getElementById(channelId).style.borderLeft = '5px solid #48bb78';
            checkAllSubscribed();
        } else {
            showMessage(data.error || 'حدث خطأ أثناء التحقق', 'error');
            document.getElementById(statusId).textContent = 'غير مشترك';
            document.getElementById(statusId).style.color = '';
            document.getElementById(channelId).style.borderLeft = '';
        }
    } catch (err) {
        console.error('Error verifying subscription:', err);
        showMessage('حدث خطأ أثناء الاتصال بالخادم', 'error');
        document.getElementById(statusId).textContent = 'غير مشترك';
        document.getElementById(statusId).style.color = '';
        document.getElementById(channelId).style.borderLeft = '';
    }
}

// Modal functions
function showModal(modalId) {
    document.getElementById(modalId).style.display = 'block';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Close modals when clicking outside
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}

// Add touch event for mobile devices
document.addEventListener('touchstart', function() {}, { passive: true });

// Watch ad function

function watchAd() {
    document.querySelector(".btn-primary").disabled = true;

async function watchAd() {
    const today = new Date().toDateString();
    let adsWatchedToday = parseInt(localStorage.getItem('adsWatchedToday') || '0');
    const lastAdDate = localStorage.getItem('lastAdDate');

    if (lastAdDate !== today) {
        adsWatchedToday = 0;
        localStorage.setItem('lastAdDate', today);
        localStorage.setItem('adsWatchedToday', '0');
    }

    if (adsWatchedToday >= 50) {
        showMessage('لقد وصلت للحد الأقصى من الإعلانات اليوم (50 إعلان)', 'error');
        return;
    }

    showMessage('جاري تحميل الإعلان...', 'info');

    try {
        await show_9800891();
        adsWatchedToday += 1;
        localStorage.setItem('adsWatchedToday', String(adsWatchedToday));
        userData.balance = (parseFloat(userData.balance) || 0) + 0.10;
        userData.adsWatchedToday = adsWatchedToday;
        updateDisplay();

        const remaining = 50 - adsWatchedToday;
        showMessage(`تم مشاهدة الإعلان بنجاح! حصلت على 0.10 CMD\nالإعلانات المتبقية اليوم: ${remaining}`, 'success');

    } catch (err) {
        console.error('Error watching ad:', err);
        showMessage('حدث خطأ أثناء عرض الإعلان', 'error');
    }
}


// بيانات اللعبة
const imageSets = { 
    1: [
        "https://i.ibb.co/BH7c6Rhn/cyber-knight.png",
        "https://i.ibb.co/GQXN4jK9/copilot-image-1758640119888.png", 
        "https://i.ibb.co/93yQx0rC/copilot-image-1759163390948.png"
    ], 
    2: [
        "https://i.ibb.co/hxmHNWMt/copilot-image-1758638698976.png", 
        "https://i.ibb.co/kVjS5kMV/image-1759163544895.jpg"
    ],
    3: [
        "https://i.ibb.co/S4ZG2pPj/copilot-image-1758637989408.png", 
        "https://i.ibb.co/Gvy2P3vR/copilot-image-1759164220146.png"
    ],
    4: [
        "https://i.ibb.co/TD4Mzgrh/image-1758953439203.jpg"
    ],
    5: [
        "https://i.ibb.co/V0m2wQ6y/image-1758974208483.jpg", 
        "https://i.ibb.co/Z7ML3Qx/image-1759163756054.jpg"
    ]
};

const correctImages = [
    "https://i.ibb.co/Gvy2P3vR/copilot-image-1759164220146.png",
    "https://i.ibb.co/93yQx0rC/copilot-image-1759163390948.png",
    "https://i.ibb.co/Z7ML3Qx/image-1759163756054.jpg"
];


let selectedImages = [];
let gameScore = 0;
let gameLocked = false;

// تهيئة اللعبة
function initComboGame() {
    loadGameScore();
    updateComboGameButton();
    preloadGameImages();
}

// تحميل الصور مسبقاً لتحسين الأداء
function preloadGameImages() {
    const allImages = [...new Set([].concat(...Object.values(imageSets)))];
    allImages.forEach(src => {
        const img = new Image();
        img.src = src;
    });
}

// وظائف التنقل في اللعبة
function startComboGame() {
    if (!canPlayGame()) {
        showMessage('يجب الانتظار 24 ساعة بين كل محاولة لعب', 'error');
        return;
    }
    
    document.getElementById("game-main-page").style.display = "none";
    document.getElementById("game-page").style.display = "block";
}

function goBackFromGame() {
    document.getElementById("game-page").style.display = "none";
    document.getElementById("game-main-page").style.display = "block";
    resetGameState();
    updateComboGameButton();
}

// نظام النقاط والوقت في اللعبة
function loadGameScore() {
    const savedScore = localStorage.getItem('comboGameScore');
    if (savedScore) {
        gameScore = parseInt(savedScore);
        document.getElementById("game-score").textContent = gameScore;
    }
}

function saveGameScore() {
    localStorage.setItem('comboGameScore', gameScore);
}

function canPlayGame() {
    const lastPlayTime = localStorage.getItem('comboGameLastPlay');
    if (!lastPlayTime) return true;
    
    const now = new Date().getTime();
    const lastPlay = parseInt(lastPlayTime);
    const twentyFourHours = 24 * 60 * 60 * 1000; // 24 ساعة بالمللي ثانية
    
    return (now - lastPlay) >= twentyFourHours;
}

function updateLastPlayTime() {
    localStorage.setItem('comboGameLastPlay', new Date().getTime());
    updateComboGameButton(); // تحديث الزر فوراً بعد تحديث الوقت
}

function updateComboGameButton() {
    const playButton = document.getElementById('game-play-button');
    const timeMessage = document.getElementById('game-time-message');
    
    if (canPlayGame()) {
        playButton.disabled = false;
        playButton.textContent = 'ابدأ اللعب';
        playButton.style.background = 'linear-gradient(45deg, #ff6b6b, #4ecdc4)';
        timeMessage.style.display = 'none';
    } else {
        playButton.disabled = true;
        playButton.textContent = '⏳ انتظر';
        playButton.style.background = 'linear-gradient(45deg, #888, #666)';
        
        const lastPlayTime = localStorage.getItem('comboGameLastPlay');
        const now = new Date().getTime();
        const nextPlayTime = parseInt(lastPlayTime) + (24 * 60 * 60 * 1000);
        const timeLeft = nextPlayTime - now;
        
        if (timeLeft > 0) {
            const hours = Math.floor(timeLeft / (1000 * 60 * 60));
            const minutes = Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((timeLeft % (1000 * 60)) / 1000);
            
            timeMessage.textContent = `يمكنك اللعب مرة أخرى بعد ${hours} ساعة و ${minutes} دقيقة و ${seconds} ثانية`;
            timeMessage.style.display = 'block';
            
            // تحديث العد التنازلي كل ثانية
            setTimeout(updateComboGameButton, 1000);
        } else {
            // إذا انتهى الوقت، تفعيل الزر
            playButton.disabled = false;
            playButton.textContent = 'ابدأ اللعب';
            playButton.style.background = 'linear-gradient(45deg, #ff6b6b, #4ecdc4)';
            timeMessage.style.display = 'none';
        }
    }
}

// منطق اللعبة
function showGameContent(num) {
    if (gameLocked) return;

    // إخفاء جميع الصناديق
    for (let i = 1; i <= 5; i++) {
        const box = document.getElementById("game-content" + i);
        box.style.display = "none";
        box.innerHTML = "";
    }

    // إظهار الصندوق المحدد
    const content = document.getElementById("game-content" + num);
    content.style.display = "block";

    // إنشاء شبكة الصور
    const grid = document.createElement("div");
    grid.className = "game-image-grid";

    imageSets[num].forEach((src, i) => {
        const cell = document.createElement("div");
        cell.className = "game-cell";
        cell.style.animationDelay = `${i * 0.1}s`;

        const img = document.createElement("img");
        img.src = src;
        img.loading = "lazy";
        img.onclick = () => selectGameImage(src, cell);
        cell.appendChild(img);

        grid.appendChild(cell);
    });

    content.appendChild(grid);
}

function selectGameImage(src, cellElement) {
    if (gameLocked || selectedImages.length >= 3 || selectedImages.includes(src)) return;
    
    selectedImages.push(src);
    
    const box = document.getElementById("game-chosen" + selectedImages.length);
    const img = document.createElement("img");
    img.src = src;
    img.alt = "صورة مختارة";
    box.innerHTML = "";
    box.appendChild(img);
    
    cellElement.classList.add("clicked");
    setTimeout(() => cellElement.classList.remove("clicked"), 300);
    
    if (selectedImages.length === 3) {
        gameLocked = true;
        setTimeout(checkGameScore, 500);
    }
}

function checkGameScore() {
    const isCorrect = selectedImages.every(img => correctImages.includes(img));
    const resultMessage = document.getElementById("game-result-message");
    
    // ✅ تحديث وقت اللعبة أولاً بغض النظر عن النتيجة
    updateLastPlayTime();
    
    if (isCorrect) {
        gameScore += 1;
        document.getElementById("game-score").textContent = gameScore;
        resultMessage.textContent = "مبروك! لقد ربحت 1 CMD! 🎉";
        resultMessage.className = "game-result-message game-win";
        
        saveGameScore();
        
        // ✅ إضافة مكافأة للرصيد وحفظها في الخادم
        userData.balance += 3;
        updateDisplay();
        saveUserData();
        
        // ✅ حفظ النتيجة في الخادم
        saveGameResultToServer(3, 3);
        
        showMessage('مبروك! فزت بـ 3 CMD مكافأة!', 'success');
    } else {
        resultMessage.textContent = "للأسف، لم تربح هذه المرة 😔";
        resultMessage.className = "game-result-message game-lose";
        
        // ✅ حفظ النتيجة في الخادم (0 نقاط)
        saveGameResultToServer(0, 0);
    }
    
    resultMessage.style.display = "block";
    
    // إعادة تعيين اللعبة بعد 3 ثواني
    setTimeout(() => {
        resetGameState();
        setTimeout(() => {
            goBackFromGame();
        }, 500);
    }, 3000);
}

// ✅ دالة جديدة لحفظ نتيجة اللعبة في الخادم
async function saveGameResultToServer(score, reward) {
    try {
        const response = await fetch(`${API_BASE}/game/update-score`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userId: userData.id,
                gameType: 'combo',
                score: score,
                reward: reward
            })
        });

        const data = await response.json();
        
        if (data.success) {
            console.log('✅ Game result saved on server');
        } else {
            console.error('❌ Error saving game result on server:', data.error);
        }
    } catch (err) {
        console.error('❌ Network error saving game result:', err);
    }
}

function resetGameState() {
    selectedImages = [];
    gameLocked = false;
    
    document.getElementById("game-chosen1").innerHTML = "1";
    document.getElementById("game-chosen2").innerHTML = "2";
    document.getElementById("game-chosen3").innerHTML = "3";
    
    for (let i = 1; i <= 5; i++) {
        document.getElementById("game-content" + i).style.display = "none";
        document.getElementById("game-content" + i).innerHTML = "";
    }
    
    document.getElementById("game-result-message").style.display = "none";
}
