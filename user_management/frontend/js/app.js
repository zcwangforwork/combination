const API_BASE = 'http://localhost:8080/api';

const { createApp, ref, reactive, computed, watch, onMounted } = Vue;

const app = createApp({
    setup() {
        // ===== State =====
        const isLoggedIn = ref(false);
        const loginLoading = ref(false);
        const loginError = ref('');
        const loginForm = reactive({ username: '', password: '' });
        const loginRules = {
            username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
            password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
        };

        // Current user
        const currentUserName = ref('');
        const currentRole = ref('');
        const currentRoleName = ref('');
        const token = ref('');

        // UI
        const activeMenu = ref('dashboard');
        const searchKeyword = ref('');
        const filterDepartmentId = ref(null);
        const filterRoleCode = ref(null);
        const filterEnabled = ref(null);

        // Dashboard
        const dashboardStats = ref({
            totalEmployees: 0, activeEmployees: 0, totalDepartments: 0, totalRoles: 0,
            employeesByRole: {}, employeesByDepartment: {}
        });
        const statCards = computed(() => [
            { label: '员工总数', value: dashboardStats.value.totalEmployees, color: '#409eff',
                icon: 'UserFilled' },
            { label: '在职员工', value: dashboardStats.value.activeEmployees, color: '#67c23a',
                icon: 'User' },
            { label: '部门数', value: dashboardStats.value.totalDepartments, color: '#e6a23c',
                icon: 'OfficeBuilding' },
            { label: '角色数', value: dashboardStats.value.totalRoles, color: '#f56c6c',
                icon: 'Avatar' },
        ]);

        // Employee list
        const employeeList = ref([]);
        const tableLoading = ref(false);
        const currentPage = ref(1);
        const pageSize = ref(20);
        const totalEmployees = ref(0);

        // Dialog
        const dialogVisible = ref(false);
        const dialogTitle = ref('添加员工');
        const isEdit = ref(false);
        const editId = ref(null);
        const submitLoading = ref(false);
        const empForm = reactive({
            username: '', realName: '', password: '', employeeNo: '',
            roleCode: '', departmentName: '', email: '', phone: '', enabled: true
        });
        const empRules = {
            username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
            realName: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
            roleCode: [{ required: true, message: '请选择角色', trigger: 'change' }],
            email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
        };

        // Departments & Roles
        const departments = ref([]);
        const roles = ref([]);
        const showDeptDialog = ref(false);
        const deptForm = reactive({ name: '', description: '' });

        // ===== Department Leader State =====
        const showLeaderDialog = ref(false);
        const leaderDialogDept = ref(null);
        const leaderForm = reactive({ leaderId: null });
        const deptMembersForLeader = ref([]);

        // ===== Confidentiality Access State =====
        const showConfAccessDialog = ref(false);
        const confAccessTargetUser = ref(null);
        const confAccessList = ref([]);
        const confAccessForm = reactive({ level: '', mode: 'READ_ONLY' });

        // ===== Category Access (RESEARCH 资料分类授权) =====
        // 注：researchCategories 复用研发资料模块的声明（第 151 行），此处不重复声明
        const showCategoryAccessDialog = ref(false);
        const categoryAccessTargetUser = ref(null);
        const categoryAccessList = ref([]);
        const categoryAccessSelectedIds = ref([]);
        const categoryAccessMode = ref('READ_ONLY');

        // ===== Document Access (按资料授权：ADMIN 授权某员工查看某份具体研发资料) =====
        const showDocumentAccessDialog = ref(false);
        const documentAccessTargetUser = ref(null);
        const documentAccessList = ref([]);
        const documentAccessForm = reactive({ documentId: null });
        // 授权选择器用：ADMIN 视角的全部研发资料（view=all）
        const allResearchMaterials = ref([]);

        // ===== Document Management State =====
        const documentList = ref([]);
        const docLoading = ref(false);
        const docCurrentPage = ref(1);
        const docPageSize = ref(20);
        const docTotal = ref(0);
        const docSearchKeyword = ref('');
        const docCategoryFilter = ref(null);
        const categories = ref([]);

        // Upload dialog
        const uploadDialogVisible = ref(false);
        const uploadLoading = ref(false);
        const uploadForm = reactive({
            file: null,
            title: '',
            categoryId: null,
            description: '',
            visibility: 'PUBLIC',
        });

        // Preview dialog
        const previewDialogVisible = ref(false);
        const previewUrl = ref('');
        const previewTitle = ref('');
        const previewIsImage = ref(false);
        const previewIsPdf = ref(false);
        const previewIsOffice = ref(false);

        // Whether current user can upload/delete docs
        const canUploadDoc = computed(() =>
            currentRole.value === 'ADMIN' || currentRole.value === 'SYSTEM_ENGINEER');
        const canDeleteDoc = computed(() => currentRole.value === 'ADMIN');
        // Publish: same as upload (ADMIN, SYSTEM_ENGINEER); Rollback: ADMIN only
        const canPublishDoc = computed(() =>
            currentRole.value === 'ADMIN' || currentRole.value === 'SYSTEM_ENGINEER');
        const canRollbackDoc = computed(() => currentRole.value === 'ADMIN');
        // Approve/Reject/Retire: ADMIN only (审批工作流)
        const canApproveDoc = computed(() => currentRole.value === 'ADMIN');

        // Publish dialog
        const publishDialogVisible = ref(false);
        const publishLoading = ref(false);
        const publishForm = reactive({ changeLog: '', password: '', meaning: '' });
        const currentDocForPublish = ref(null);

        // Review decision dialog (approve/reject)
        const reviewDialogVisible = ref(false);
        const reviewLoading = ref(false);
        const reviewForm = reactive({ action: '', comment: '', password: '', meaning: '' });
        const currentDocForReview = ref(null);

        // Generic signature dialog (retire/rollback 等需要电子签名的操作)
        const signDialogVisible = ref(false);
        const signLoading = ref(false);
        const signForm = reactive({ password: '', meaning: '' });
        const currentSignAction = ref(null);  // { type: 'retire'|'rollback', docId, revId?, revVersion? }

        // Revision history dialog
        const revisionDialogVisible = ref(false);
        const revisionList = ref([]);
        const revisionLoading = ref(false);
        const currentDocForRevision = ref(null);

        // ===== Research Material State =====
        const researchMaterialList = ref([]);
        const rmLoading = ref(false);
        const rmCurrentPage = ref(1);
        const rmPageSize = ref(20);
        const rmTotal = ref(0);
        const rmSearchKeyword = ref('');
        const rmCategoryFilter = ref(null);
        const rmView = ref('mine');  // mine / shared / all (ADMIN only)
        const researchCategories = ref([]);

        // Research upload/edit dialog
        const rmUploadDialogVisible = ref(false);
        const rmUploadLoading = ref(false);
        const rmIsEdit = ref(false);
        const rmEditId = ref(null);
        const rmUploadForm = reactive({
            file: null,
            title: '',
            categoryId: null,
            description: '',
            confidentialityLevel: 'INTERNAL',
        });

        // Share dialog
        const shareDialogVisible = ref(false);
        const shareLoading = ref(false);
        const currentRmForShare = ref(null);
        const shareForm = reactive({ userIds: [] });
        const shareableUsers = ref([]);
        const shareList = ref([]);

        // Confidentiality level quick-edit dialog
        const rmConfDialogVisible = ref(false);
        const rmConfLoading = ref(false);
        const currentRmForConf = ref(null);
        const rmConfForm = reactive({ confidentialityLevel: 'INTERNAL' });

        // ===== Research Data (研发数据) =====
        const researchDataList = ref([]);
        const rdLoading = ref(false);
        const rdCurrentPage = ref(1);
        const rdPageSize = ref(20);
        const rdTotal = ref(0);
        const rdSearchKeyword = ref('');
        const rdCategoryFilter = ref(null);
        const rdTypeFilter = ref(null);
        const rdParamCategoryFilter = ref(null);
        const rdView = ref('mine');

        // 录入/编辑对话框
        const rdEditDialogVisible = ref(false);
        const rdEditLoading = ref(false);
        const rdIsEdit = ref(false);
        const rdEditId = ref(null);
        const rdForm = reactive({
            recordType: 'TEST_RECORD',
            recordNo: '', title: '', recordDate: '', operator: '',
            status: 'DRAFT', deviceModel: '', batchNo: '',
            confidentialityLevel: 'INTERNAL', categoryId: null, description: '',
            // TEST_RECORD 扩展
            testItem: '', flowRate: '', medium: '', temperature: '', duration: '',
            measuredResult: '', testSpec: '', passFail: '', testEquipment: '',
            // DESIGN_PARAM 扩展
            paramName: '', paramValue: '', unit: '', dpSpec: '', dpVersion: '', changeReason: '',
            // EXPERIMENT 扩展
            objective: '', method: '', expParams: '', observation: '', conclusion: '',
            // FAILURE 扩展
            phenomenon: '', rootCause: '', failAction: '', trackingNo: '', resolvedAt: '',
            // RISK 扩展 (ISO 14971)
            hazardType: '', failureMode: '', severity: null, occurrence: null, detection: null,
            controlMeasure: '', residualRisk: '', traceToDesign: '',
            // BIOCOMPAT 扩展 (GB/T 16886)
            bioTestItem: '', material: '', extractCondition: '', bioTestOrg: '', bioReportNo: '',
            bioTestResult: '', bioConclusion: '',
            // SOFTWARE_VV 扩展 (IEC 62304)
            swVersion: '', safetyClass: '', testLevel: '', swTestResult: '', defectCount: null,
            traceMatrix: '', swTestReport: '',
            // EMC_SAFETY 扩展 (GB 9706 / YY 9706)
            emcTestItem: '', emcStandard: '', emcMeasured: '', emcLimit: '', emcPassFail: '',
            emcEquipment: '', emcTestOrg: '',
            // CLINICAL 扩展
            evalPath: '', compareDevice: '', differenceAnalysis: '', literatureSummary: '',
            evalReportNo: '', clinicalConclusion: '',
            // VALIDATION 扩展 (验证/确认)
            validationType: '', vStandard: '', vScope: '', acceptanceCriteria: '',
            vSamples: '', vProtocolNo: '', vReportNo: '', vResult: '', vConclusion: '',
            vReviewer: '', vApprover: '',
            // MATERIAL 扩展 (物料/来料检验)
            materialName: '', materialCode: '', materialSupplier: '', materialSpec: '',
            iqcItem: '', iqcStandard: '', sampleQty: '', iqcResult: '', iqcReportNo: '',
            coaAvailable: '', storageCondition: '', materialExpiry: '',
            // STERILIZATION 扩展 (灭菌/包装/货架寿命)
            sterMethod: '', sterParameter: '', sterLoad: '', sterVerification: '',
            sterResult: '', packTestItem: '', packTestResult: '', shelfLife: '',
            agingType: '', agingPeriod: '', sterReportNo: '',
            // CHANGE 扩展 (变更/偏差/CAPA)
            changeType: '', changeNo: '', changeReason: '', riskAssessment: '',
            impactScope: '', actionPlan: '', changeDate: '', effectVerify: '', changeApprover: '',
            // OTHER 动态自定义字段
            dynamicFields: [],
        });

        // 修改保密等级对话框
        const rdConfDialogVisible = ref(false);
        const rdConfLoading = ref(false);
        const currentRdForConf = ref(null);
        const rdConfForm = reactive({ confidentialityLevel: 'INTERNAL' });

        // 详情对话框
        const rdDetailDialogVisible = ref(false);
        const currentRdDetail = ref(null);

        // ===== Suppliers (供应商) =====
        const supplierList = ref([]);
        const enabledSuppliers = ref([]);
        const supplierLoading = ref(false);
        const supplierCurrentPage = ref(1);
        const supplierPageSize = ref(20);
        const supplierTotal = ref(0);
        const supplierSearchKeyword = ref('');
        const supplierCategoryFilter = ref(null);
        const supplierQualificationFilter = ref(null);
        const supplierEditDialogVisible = ref(false);
        const supplierDetailDialogVisible = ref(false);
        const supplierSubmitting = ref(false);
        const supplierIsEdit = ref(false);
        const supplierEditId = ref(null);
        const supplierDetail = ref({});
        const supplierForm = reactive({
            supplierCode: '', name: '', category: '', contact: '', phone: '', email: '',
            qualificationStatus: 'PENDING', qualityContactName: '', qualityContactPhone: '',
            enabled: true, optimisticLockVersion: null,
        });
        const supplierRules = {
            supplierCode: [{ required: true, message: '请输入供应商编码', trigger: 'blur' }],
            name: [{ required: true, message: '请输入供应商名称', trigger: 'blur' }],
        };

        // ===== Commercial Records (商业成本记录) =====
        const commercialRecordList = ref([]);
        const crLoading = ref(false);
        const crCurrentPage = ref(1);
        const crPageSize = ref(20);
        const crTotal = ref(0);
        const crSearchKeyword = ref('');
        const crSupplierFilter = ref(null);
        const crView = ref('mine');
        const crEditDialogVisible = ref(false);
        const crDetailDialogVisible = ref(false);
        const crSubmitting = ref(false);
        const crIsEdit = ref(false);
        const crEditId = ref(null);
        const crDetail = ref({});
        const crForm = reactive({
            supplierId: null, itemName: '', costPrice: null, currency: 'CNY',
            effectiveDate: '', confidentialityLevel: 'CONFIDENTIAL', description: '',
            optimisticLockVersion: null,
        });
        const crRules = {
            supplierId: [{ required: true, message: '请选择供应商', trigger: 'change' }],
            itemName: [{ required: true, message: '请输入物料/项目名称', trigger: 'blur' }],
            costPrice: [{ required: true, message: '请输入成本价', trigger: 'blur' }],
            effectiveDate: [{ required: true, message: '请选择生效日期', trigger: 'change' }],
        };

        // Page title
        const pageTitle = computed(() => {
            const map = {
                dashboard: '工作台',
                employees: '员工管理',
                departments: '部门管理',
                documents: '体系文档',
                'research-materials': '研发资料',
                'research-data': '研发数据',
                'suppliers': '供应商管理',
                'commercial-records': '商业成本记录',
                'agent-chat': 'AI 文档写作',
            };
            return map[activeMenu.value] || '工作台';
        });

        // ===== Axios setup =====
        const api = axios.create({ baseURL: API_BASE });
        api.interceptors.request.use(config => {
            if (token.value) config.headers.Authorization = `Bearer ${token.value}`;
            return config;
        });
        api.interceptors.response.use(
            res => res,
            err => {
                if (err.response && err.response.status === 401) {
                    ElementPlus.ElMessage.warning('登录已过期，请重新登录');
                    handleLogout();
                }
                return Promise.reject(err);
            }
        );

        // ===== Notifications (通知待办) =====
        const notifUnread = ref(0);
        const notifTodoCount = ref(0);
        const notifDrawerVisible = ref(false);
        const notifTab = ref('todos');
        const notifTodos = ref([]);
        const notifList = ref([]);
        const notifTotal = ref(0);
        const notifPage = ref(1);
        const notifPageSize = ref(20);
        const notifLoading = ref(false);
        const announceDialogVisible = ref(false);
        const announceForm = reactive({ title: '', content: '' });
        const announceSubmitting = ref(false);
        let notifTimer = null;

        const loadNotificationStats = async () => {
            if (!isLoggedIn.value) return;
            try {
                const res = await api.get('/notifications/stats');
                notifUnread.value = res.data.data.unreadCount || 0;
                notifTodoCount.value = res.data.data.todoCount || 0;
            } catch (e) {
                // 轮询失败静默，不打扰用户
            }
        };

        const loadTodos = async () => {
            try {
                const res = await api.get('/notifications/todos');
                notifTodos.value = res.data.data || [];
            } catch (e) {
                notifTodos.value = [];
            }
        };

        const loadNotifications = async () => {
            notifLoading.value = true;
            try {
                const res = await api.get('/notifications', {
                    params: { page: notifPage.value - 1, size: notifPageSize.value }
                });
                notifList.value = res.data.data.content || [];
                notifTotal.value = res.data.data.totalElements || 0;
            } catch (e) {
                ElementPlus.ElMessage.error('加载通知失败');
            } finally {
                notifLoading.value = false;
            }
        };

        const openNotificationDrawer = () => {
            notifDrawerVisible.value = true;
            loadTodos();
            loadNotifications();
        };

        const handleNotifTabChange = (tab) => {
            notifTab.value = tab;
            if (tab === 'all') loadNotifications();
        };

        const handleNotifPageChange = (page) => {
            notifPage.value = page;
            loadNotifications();
        };

        const handleNotificationClick = async (n) => {
            if (!n.read) {
                try {
                    await api.put(`/notifications/${n.id}/read`);
                    n.read = true;
                    loadNotificationStats();
                } catch (e) { /* 已读失败不阻塞跳转 */ }
            }
            // 根据关联业务跳转到对应页面
            if (n.relatedType === 'DOCUMENT') {
                activeMenu.value = 'documents';
                loadCategories();
                loadDocuments();
            } else if (n.relatedType === 'RESEARCH_MATERIAL') {
                activeMenu.value = 'research-materials';
                loadResearchCategories();
                loadResearchMaterials();
            } else if (n.relatedType === 'USER') {
                activeMenu.value = 'employees';
                loadEmployees();
            }
            notifDrawerVisible.value = false;
        };

        const handleMarkAllRead = async () => {
            try {
                await api.put('/notifications/read-all');
                notifUnread.value = 0;
                notifTodoCount.value = 0;
                loadTodos();
                loadNotifications();
                ElementPlus.ElMessage.success('已全部标记为已读');
            } catch (e) {
                ElementPlus.ElMessage.error('操作失败');
            }
        };

        const openAnnounceDialog = () => {
            announceForm.title = '';
            announceForm.content = '';
            announceDialogVisible.value = true;
        };

        const handlePublishAnnouncement = async () => {
            if (!announceForm.title || !announceForm.title.trim()
                || !announceForm.content || !announceForm.content.trim()) {
                ElementPlus.ElMessage.warning('请填写公告标题和内容');
                return;
            }
            announceSubmitting.value = true;
            try {
                await api.post('/notifications/announcement', { ...announceForm });
                ElementPlus.ElMessage.success('公告已发布');
                announceDialogVisible.value = false;
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '发布失败');
            } finally {
                announceSubmitting.value = false;
            }
        };

        const notifTypeTag = (type) => {
            const map = {
                APPROVAL_TASK: 'danger', APPROVAL_RESULT: 'warning',
                CONFIDENTIALITY_GRANT: 'info', CATEGORY_GRANT: 'info',
                DOCUMENT_SHARE: 'success', SYSTEM_ANNOUNCEMENT: 'primary'
            };
            return map[type] || 'info';
        };

        const formatDateTime = (iso) => {
            if (!iso) return '';
            const d = new Date(iso);
            if (isNaN(d.getTime())) return iso;
            const p = (n) => String(n).padStart(2, '0');
            return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
        };

        // ===== Auth =====
        const handleLogin = async () => {
            loginError.value = '';
            loginLoading.value = true;
            try {
                const res = await axios.post(`${API_BASE}/auth/login`, {
                    username: loginForm.username,
                    password: loginForm.password,
                });
                const data = res.data.data;
                token.value = data.token;
                currentUserName.value = data.realName;
                currentRole.value = data.roleCode;
                currentRoleName.value = data.roleName;

                localStorage.setItem('token', data.token);
                localStorage.setItem('user', JSON.stringify({
                    realName: data.realName, roleCode: data.roleCode, roleName: data.roleName
                }));

                isLoggedIn.value = true;
                loginError.value = '';
                loadDashboard();
                loadEmployees();
                loadDepartments();
                loadRoles();
                loadNotificationStats();
            } catch (e) {
                loginError.value = e.response?.data?.message || '登录失败，请检查网络连接';
            } finally {
                loginLoading.value = false;
            }
        };

        const handleLogout = () => {
            token.value = '';
            currentUserName.value = '';
            currentRole.value = '';
            currentRoleName.value = '';
            isLoggedIn.value = false;
            activeMenu.value = 'dashboard';
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            // 中断 agent 进行中的 SSE 流与定时器（视图随 v-if 登录页切换而保留在 DOM，
            // 但流不应在登出后继续）
            if (window.AgentChat) AgentChat.deactivate();
            if (notifTimer) {
                clearInterval(notifTimer);
                notifTimer = null;
            }
        };

        // Session restore
        const restoreSession = () => {
            const savedToken = localStorage.getItem('token');
            const savedUser = localStorage.getItem('user');
            if (savedToken && savedUser) {
                token.value = savedToken;
                const user = JSON.parse(savedUser);
                currentUserName.value = user.realName;
                currentRole.value = user.roleCode;
                currentRoleName.value = user.roleName;
                isLoggedIn.value = true;
                loadDashboard();
                loadNotificationStats();
                loadEmployees();
                loadDepartments();
                loadRoles();
            }
        };

        // ===== Data loading =====
        const loadDashboard = async () => {
            try {
                const res = await api.get('/dashboard/stats');
                dashboardStats.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        const loadEmployees = async () => {
            tableLoading.value = true;
            try {
                const res = await api.get('/employees', {
                    params: {
                        page: currentPage.value - 1, size: pageSize.value,
                        keyword: searchKeyword.value,
                        departmentId: filterDepartmentId.value,
                        roleCode: filterRoleCode.value,
                        enabled: filterEnabled.value
                    }
                });
                const page = res.data.data;
                employeeList.value = page.content;
                totalEmployees.value = page.totalElements;
            } catch (e) { /* ignore */ }
            finally { tableLoading.value = false; }
        };

        // 筛选条件变化时回到第一页再刷新（axios 会忽略 null/undefined 参数）
        const applyEmployeeFilter = () => {
            currentPage.value = 1;
            loadEmployees();
        };

        const loadDepartments = async () => {
            try {
                const res = await api.get('/departments');
                departments.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        const loadRoles = async () => {
            try {
                const res = await api.get('/roles');
                roles.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        // ===== Employee CRUD =====
        const showAddDialog = () => {
            dialogTitle.value = '添加员工';
            isEdit.value = false;
            editId.value = null;
            resetForm();
            dialogVisible.value = true;
        };

        const showEditDialog = async (row) => {
            dialogTitle.value = '编辑员工';
            isEdit.value = true;
            editId.value = row.id;
            try {
                const res = await api.get(`/employees/${row.id}`);
                const u = res.data.data;
                empForm.username = u.username;
                empForm.realName = u.realName;
                empForm.password = '';
                empForm.employeeNo = u.employeeNo || '';
                empForm.roleCode = u.role ? u.role.code : '';
                empForm.departmentName = u.department ? u.department.name : '';
                empForm.email = u.email || '';
                empForm.phone = u.phone || '';
                empForm.enabled = u.enabled;
            } catch (e) { ElementPlus.ElMessage.error('获取员工信息失败'); return; }
            dialogVisible.value = true;
        };

        const handleSubmit = async () => {
            submitLoading.value = true;
            try {
                const payload = { ...empForm };
                if (isEdit.value) {
                    if (!payload.password) delete payload.password;
                    await api.put(`/employees/${editId.value}`, payload);
                    ElementPlus.ElMessage.success('更新成功');
                } else {
                    if (!payload.password) payload.password = '123456';
                    await api.post('/employees', payload);
                    ElementPlus.ElMessage.success('创建成功');
                }
                dialogVisible.value = false;
                loadEmployees();
                loadDashboard();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '操作失败');
            } finally {
                submitLoading.value = false;
            }
        };

        const handleDelete = async (id) => {
            try {
                await api.delete(`/employees/${id}`);
                ElementPlus.ElMessage.success('删除成功');
                loadEmployees();
                loadDashboard();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '删除失败');
            }
        };

        const resetForm = () => {
            Object.keys(empForm).forEach(k => empForm[k] = k === 'enabled' ? true : '');
        };

        // ===== Department =====
        const handleAddDept = async () => {
            if (!deptForm.name) { ElementPlus.ElMessage.warning('请输入部门名称'); return; }
            try {
                await api.post('/employees', {
                    username: 'dept_placeholder_' + Date.now(),
                    realName: '占位用户',
                    roleCode: 'ADMIN',
                    departmentName: deptForm.name,
                    enabled: false,
                });
                // Create department by creating a placeholder user with the department name
                showDeptDialog.value = false;
                deptForm.name = '';
                deptForm.description = '';
                loadDepartments();
                ElementPlus.ElMessage.success('部门已添加');
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '添加失败');
            }
        };

        // ===== Department Leader =====
        const openLeaderDialog = async (dept) => {
            leaderDialogDept.value = dept;
            leaderForm.leaderId = dept.leader ? dept.leader.id : null;
            showLeaderDialog.value = true;
            // 加载该部门成员（从 employeeList 过滤）
            try {
                const res = await api.get('/employees', { params: { page: 0, size: 999 } });
                const allUsers = res.data.data.content || [];
                deptMembersForLeader.value = allUsers.filter(u =>
                    u.department && u.department.id === dept.id);
            } catch (e) { /* ignore */ }
        };

        const handleSetLeader = async () => {
            try {
                await api.put(`/departments/${leaderDialogDept.value.id}/leader`,
                    null, { params: { leaderId: leaderForm.leaderId } });
                ElementPlus.ElMessage.success('设置成功');
                showLeaderDialog.value = false;
                loadDepartments();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '设置失败');
            }
        };

        // ===== Confidentiality Access =====
        const openConfAccessDialog = async (user) => {
            confAccessTargetUser.value = user;
            confAccessForm.level = '';
            confAccessForm.mode = 'READ_ONLY';
            showConfAccessDialog.value = true;
            await loadConfAccess(user.id);
        };

        const loadConfAccess = async (userId) => {
            try {
                const res = await api.get(`/users/${userId}/confidentiality-access`);
                confAccessList.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        const handleGrantConfAccess = async () => {
            if (!confAccessForm.level) {
                ElementPlus.ElMessage.warning('请选择保密等级');
                return;
            }
            try {
                await api.put(`/users/${confAccessTargetUser.value.id}/confidentiality-access`,
                    { confidentialityLevel: confAccessForm.level, accessMode: confAccessForm.mode });
                ElementPlus.ElMessage.success('授权成功');
                confAccessForm.level = '';
                confAccessForm.mode = 'READ_ONLY';
                await loadConfAccess(confAccessTargetUser.value.id);
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '授权失败');
            }
        };

        // 切换某保密等级授权的读写模式（幂等：同等级+新模式 PUT，后端已存在则更新模式）
        const handleToggleConfAccessMode = async (row, mode) => {
            try {
                await api.put(`/users/${confAccessTargetUser.value.id}/confidentiality-access`,
                    { confidentialityLevel: row.confidentialityLevel, accessMode: mode });
                ElementPlus.ElMessage.success(mode === 'READ_WRITE' ? '已设为可读写' : '已设为只读');
                await loadConfAccess(confAccessTargetUser.value.id);
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '切换失败');
            }
        };

        const handleRevokeConfAccess = async (level) => {
            try {
                await api.delete(`/users/${confAccessTargetUser.value.id}/confidentiality-access`,
                    { params: { confidentialityLevel: level } });
                ElementPlus.ElMessage.success('撤销成功');
                await loadConfAccess(confAccessTargetUser.value.id);
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '撤销失败');
            }
        };

        // ===== Category Access (RESEARCH 资料分类授权) =====
        // 注：loadResearchCategories 复用研发资料模块的声明（第 934 行），此处不重复声明

        const openCategoryAccessDialog = async (user) => {
            categoryAccessTargetUser.value = user;
            categoryAccessSelectedIds.value = [];
            categoryAccessMode.value = 'READ_ONLY';
            showCategoryAccessDialog.value = true;
            await Promise.all([loadResearchCategories(), loadCategoryAccess(user.id)]);
        };

        const loadCategoryAccess = async (userId) => {
            try {
                const res = await api.get(`/users/${userId}/category-access`);
                categoryAccessList.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        const handleGrantCategoryAccess = async () => {
            if (categoryAccessSelectedIds.value.length === 0) {
                ElementPlus.ElMessage.warning('请至少选择一个分类');
                return;
            }
            try {
                const res = await api.put(`/users/${categoryAccessTargetUser.value.id}/category-access`,
                    { categoryIds: categoryAccessSelectedIds.value, accessMode: categoryAccessMode.value });
                ElementPlus.ElMessage.success('授权成功');
                categoryAccessList.value = res.data.data;
                categoryAccessSelectedIds.value = [];
                categoryAccessMode.value = 'READ_ONLY';
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '授权失败');
            }
        };

        // 切换某分类授权的读写模式（单分类重授权，后端已存在则更新模式）
        const handleToggleCategoryAccessMode = async (row, mode) => {
            try {
                await api.put(`/users/${categoryAccessTargetUser.value.id}/category-access`,
                    { categoryIds: [row.categoryId], accessMode: mode });
                ElementPlus.ElMessage.success(mode === 'READ_WRITE' ? '已设为可读写' : '已设为只读');
                await loadCategoryAccess(categoryAccessTargetUser.value.id);
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '切换失败');
            }
        };

        const handleRevokeCategoryAccess = async (categoryId) => {
            try {
                await api.delete(`/users/${categoryAccessTargetUser.value.id}/category-access/${categoryId}`);
                ElementPlus.ElMessage.success('撤销成功');
                await loadCategoryAccess(categoryAccessTargetUser.value.id);
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '撤销失败');
            }
        };

        // ===== Document Access (按资料授权) =====
        const openDocumentAccessDialog = async (user) => {
            documentAccessTargetUser.value = user;
            documentAccessForm.documentId = null;
            showDocumentAccessDialog.value = true;
            await Promise.all([loadAllResearchMaterials(), loadDocumentAccess(user.id)]);
        };

        // 授权选择器：ADMIN 视角的全部研发资料（view=all，size 拉满）
        const loadAllResearchMaterials = async () => {
            try {
                const res = await api.get('/research-materials', { params: { page: 0, size: 500, view: 'all' } });
                allResearchMaterials.value = res.data.data.content || [];
            } catch (e) { /* ignore */ }
        };

        const loadDocumentAccess = async (userId) => {
            try {
                const res = await api.get(`/users/${userId}/document-access`);
                documentAccessList.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        const handleGrantDocumentAccess = async () => {
            if (!documentAccessForm.documentId) {
                ElementPlus.ElMessage.warning('请选择要授权的研发资料');
                return;
            }
            try {
                const res = await api.put(`/users/${documentAccessTargetUser.value.id}/document-access`,
                    { documentIds: [documentAccessForm.documentId] });
                ElementPlus.ElMessage.success(res.data?.message || '授权成功');
                documentAccessForm.documentId = null;
                documentAccessList.value = res.data.data;
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '授权失败');
            }
        };

        const handleRevokeDocumentAccess = async (documentId) => {
            try {
                await api.delete(`/users/${documentAccessTargetUser.value.id}/document-access/${documentId}`);
                ElementPlus.ElMessage.success('撤销成功');
                await loadDocumentAccess(documentAccessTargetUser.value.id);
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '撤销失败');
            }
        };

        // ===== Document Management =====
        const loadCategories = async () => {
            try {
                const res = await api.get('/document-categories');
                categories.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        const loadDocuments = async () => {
            docLoading.value = true;
            try {
                const params = {
                    page: docCurrentPage.value - 1,
                    size: docPageSize.value,
                };
                if (docSearchKeyword.value) params.keyword = docSearchKeyword.value;
                if (docCategoryFilter.value) params.categoryId = docCategoryFilter.value;
                const res = await api.get('/documents', { params });
                const page = res.data.data;
                documentList.value = page.content;
                docTotal.value = page.totalElements;
            } catch (e) {
                ElementPlus.ElMessage.error('加载文档列表失败');
            } finally {
                docLoading.value = false;
            }
        };

        const formatFileSize = (bytes) => {
            if (!bytes) return '0 B';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
        };

        const visibilityLabel = (v) => {
            const map = { PUBLIC: '公开', DEPARTMENT: '部门内', ASSIGNEES: '指定人员' };
            return map[v] || v;
        };

        const visibilityTagType = (v) => {
            const map = { PUBLIC: 'success', DEPARTMENT: 'warning', ASSIGNEES: 'danger' };
            return map[v] || 'info';
        };

        // Document status helpers
        const statusLabel = (s) => {
            const map = { DRAFT: '草稿', REVIEW: '审核中', PUBLISHED: '已发布', OBSOLETE: '已废弃' };
            return map[s] || (s == null ? '未迁移' : s);
        };
        const statusTagType = (s) => {
            const map = { DRAFT: 'info', REVIEW: 'warning', PUBLISHED: 'success', OBSOLETE: 'danger' };
            return map[s] || 'info';
        };

        const handleFileChange = (file) => {
            uploadForm.file = file.raw;
            // Auto-fill title from filename if empty
            if (!uploadForm.title && file.name) {
                uploadForm.title = file.name.replace(/\.[^.]+$/, '');
            }
        };

        const showUploadDialog = () => {
            resetUploadForm();
            if (categories.value.length === 0) {
                loadCategories();
            }
            uploadDialogVisible.value = true;
        };

        const resetUploadForm = () => {
            uploadForm.file = null;
            uploadForm.title = '';
            uploadForm.categoryId = null;
            uploadForm.description = '';
            uploadForm.visibility = 'PUBLIC';
        };

        const handleUpload = async () => {
            if (!uploadForm.file) {
                ElementPlus.ElMessage.warning('请选择文件');
                return;
            }
            if (!uploadForm.title) {
                ElementPlus.ElMessage.warning('请输入文档标题');
                return;
            }
            if (!uploadForm.categoryId) {
                ElementPlus.ElMessage.warning('请选择文档分类');
                return;
            }

            // Client-side size check (50 MB)
            if (uploadForm.file.size > 50 * 1024 * 1024) {
                ElementPlus.ElMessage.error('文件大小不能超过 50 MB');
                return;
            }

            uploadLoading.value = true;
            try {
                const formData = new FormData();
                formData.append('file', uploadForm.file);
                formData.append('title', uploadForm.title);
                formData.append('categoryId', uploadForm.categoryId);
                formData.append('description', uploadForm.description || '');
                formData.append('visibility', uploadForm.visibility);

                await api.post('/documents/upload', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                });
                ElementPlus.ElMessage.success('上传成功，文档已创建为草稿，需发布后生效');
                uploadDialogVisible.value = false;
                loadDocuments();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '上传失败');
            } finally {
                uploadLoading.value = false;
            }
        };

        /**
         * 下载文档：fetch + Authorization 头 + Blob + URL.createObjectURL
         * 避免 JWT 泄漏到 URL/日志/Referer
         */
        const handleDownload = async (row) => {
            try {
                const res = await fetch(`${API_BASE}/documents/${row.id}/download`, {
                    headers: { 'Authorization': `Bearer ${token.value}` },
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.message || `下载失败 (${res.status})`);
                }
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = row.fileName || row.title;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (e) {
                ElementPlus.ElMessage.error(e.message || '下载失败');
            }
        };

        /**
         * 在线预览：PDF/图片直接预览，Office 文档提示下载
         */
        const handlePreview = async (row) => {
            const ext = (row.fileExtension || '').toLowerCase();

            // Office 文档不支持在线预览
            if (['doc', 'docx', 'xls', 'xlsx'].includes(ext)) {
                ElementPlus.ElMessage.info('Office 文档暂不支持在线预览，请下载查看');
                return;
            }

            // PDF 与图片直接预览
            if (!['pdf', 'jpg', 'jpeg', 'png', 'gif'].includes(ext)) {
                ElementPlus.ElMessage.warning('该文件类型不支持在线预览');
                return;
            }

            try {
                const res = await fetch(`${API_BASE}/documents/${row.id}/preview`, {
                    headers: { 'Authorization': `Bearer ${token.value}` },
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.message || `预览失败 (${res.status})`);
                }
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);

                // 清理上一次的预览 URL
                if (previewUrl.value) {
                    URL.revokeObjectURL(previewUrl.value);
                }
                previewUrl.value = url;
                previewTitle.value = row.title;
                previewIsImage.value = ['jpg', 'jpeg', 'png', 'gif'].includes(ext);
                previewIsPdf.value = ext === 'pdf';
                previewIsOffice.value = false;
                previewDialogVisible.value = true;
            } catch (e) {
                ElementPlus.ElMessage.error(e.message || '预览失败');
            }
        };

        const closePreview = () => {
            if (previewUrl.value) {
                URL.revokeObjectURL(previewUrl.value);
            }
            previewUrl.value = '';
            previewDialogVisible.value = false;
        };

        const handleDeleteDoc = async (row) => {
            try {
                await api.delete(`/documents/${row.id}`);
                ElementPlus.ElMessage.success('删除成功');
                loadDocuments();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '删除失败');
            }
        };

        // ===== Document Version Control =====

        /**
         * 打开发布对话框
         * DRAFT -> PUBLISHED (首次发布)
         * PUBLISHED -> PUBLISHED (发布新版本)
         */
        const showPublishDialog = (row) => {
            currentDocForPublish.value = row;
            publishForm.changeLog = '';
            publishForm.password = '';
            publishForm.meaning = '';
            publishDialogVisible.value = true;
        };

        /**
         * 提交发布请求
         */
        const submitPublish = async () => {
            if (!currentDocForPublish.value) return;
            // 电子签名参数校验
            if (!publishForm.password.trim()) {
                ElementPlus.ElMessage.warning('请输入签名密码');
                return;
            }
            if (!publishForm.meaning.trim()) {
                ElementPlus.ElMessage.warning('请填写签名含义');
                return;
            }
            publishLoading.value = true;
            try {
                const docId = currentDocForPublish.value.id;
                const body = {
                    changeLog: publishForm.changeLog || null,
                    password: publishForm.password,
                    meaning: publishForm.meaning
                };
                const res = await api.post(`/documents/${docId}/publish`, body);
                ElementPlus.ElMessage.success('发布成功');
                publishDialogVisible.value = false;
                loadDocuments();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '发布失败');
            } finally {
                publishLoading.value = false;
            }
        };

        // ===== 审批工作流方法 =====

        /**
         * 提交评审 DRAFT -> REVIEW
         */
        const submitForReview = async (row) => {
            try {
                await api.post(`/documents/${row.id}/submit-review`);
                ElementPlus.ElMessage.success('已提交评审，等待管理员审批');
                loadDocuments();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '提交评审失败');
            }
        };

        /**
         * 打开审批对话框（approve / reject）
         */
        const showReviewDialog = (row, action) => {
            currentDocForReview.value = row;
            reviewForm.action = action;
            reviewForm.comment = '';
            reviewDialogVisible.value = true;
        };

        /**
         * 提交审批决策
         */
        const submitReviewDecision = async () => {
            if (!currentDocForReview.value) return;
            if (reviewForm.action === 'reject' && !reviewForm.comment.trim()) {
                ElementPlus.ElMessage.warning('驳回必须填写审批意见');
                return;
            }
            reviewLoading.value = true;
            try {
                const docId = currentDocForReview.value.id;
                const body = { comment: reviewForm.comment || null };
                await api.post(`/documents/${docId}/${reviewForm.action}`, body);
                ElementPlus.ElMessage.success(reviewForm.action === 'approve' ? '审批通过' : '已驳回');
                reviewDialogVisible.value = false;
                loadDocuments();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '审批操作失败');
            } finally {
                reviewLoading.value = false;
            }
        };

        /**
         * 作废文档 PUBLISHED -> OBSOLETE
         */
        const retireDoc = async (row) => {
            try {
                await api.post(`/documents/${row.id}/retire`);
                ElementPlus.ElMessage.success('已作废');
                loadDocuments();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '作废失败');
            }
        };

        /**
         * 加载修订历史
         */
        const loadRevisions = async (row) => {
            currentDocForRevision.value = row;
            revisionDialogVisible.value = true;
            revisionLoading.value = true;
            revisionList.value = [];
            try {
                const res = await api.get(`/documents/${row.id}/revisions`);
                revisionList.value = res.data.data || [];
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '加载修订历史失败');
            } finally {
                revisionLoading.value = false;
            }
        };

        /**
         * 回滚到指定修订版本（非破坏性，创建新版本）
         */
        const handleRollback = async (rev) => {
            if (!currentDocForRevision.value) return;
            const docId = currentDocForRevision.value.id;
            try {
                await api.post(`/documents/${docId}/rollback/${rev.id}`);
                ElementPlus.ElMessage.success(`已回滚到版本 ${rev.version}`);
                // 刷新修订列表与文档列表
                loadRevisions(currentDocForRevision.value);
                loadDocuments();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '回滚失败');
            }
        };

        /**
         * 下载指定修订版本的文件
         */
        const handleDownloadRevision = async (rev) => {
            if (!currentDocForRevision.value) return;
            const docId = currentDocForRevision.value.id;
            try {
                const res = await fetch(
                    `${API_BASE}/documents/revisions/${rev.id}/download?documentId=${docId}`,
                    { headers: { 'Authorization': `Bearer ${token.value}` } }
                );
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.message || `下载失败 (${res.status})`);
                }
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = rev.fileName || `revision-${rev.version}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (e) {
                ElementPlus.ElMessage.error(e.message || '下载失败');
            }
        };

        // ===== Research Materials =====

        const loadResearchCategories = async () => {
            try {
                const res = await api.get('/document-categories', { params: { docType: 'RESEARCH' } });
                researchCategories.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        const loadResearchMaterials = async () => {
            rmLoading.value = true;
            try {
                const params = {
                    page: rmCurrentPage.value - 1,
                    size: rmPageSize.value,
                    view: rmView.value,
                };
                if (rmSearchKeyword.value) params.keyword = rmSearchKeyword.value;
                if (rmCategoryFilter.value) params.categoryId = rmCategoryFilter.value;
                const res = await api.get('/research-materials', { params });
                const page = res.data.data;
                researchMaterialList.value = page.content;
                rmTotal.value = page.totalElements;
            } catch (e) {
                ElementPlus.ElMessage.error('加载研发资料列表失败');
            } finally {
                rmLoading.value = false;
            }
        };

        const accessRoleLabel = (r) => {
            const map = { owner: '我的', shared: '分享给我', admin: '管理员', leader: '部门负责人', viewer: '可见' };
            return map[r] || r;
        };
        const accessRoleTagType = (r) => {
            const map = { owner: 'success', shared: 'warning', admin: 'danger', leader: 'primary', viewer: 'info' };
            return map[r] || 'info';
        };

        const confidentialityLabel = (c) => {
            const map = { PUBLIC: '公开', INTERNAL: '内部', CONFIDENTIAL: '机密', TOP_SECRET: '绝密' };
            return map[c] || '未设';
        };
        const confidentialityTagType = (c) => {
            const map = { PUBLIC: 'success', INTERNAL: '', CONFIDENTIAL: 'warning', TOP_SECRET: 'danger' };
            return map[c] || 'info';
        };
        const accessModeLabel = (m) => {
            return m === 'READ_WRITE' ? '可读写' : '只读';
        };

        const handleRmFileChange = (file) => {
            rmUploadForm.file = file.raw;
            if (!rmUploadForm.title && file.name) {
                rmUploadForm.title = file.name.replace(/\.[^.]+$/, '');
            }
        };

        const resetRmUploadForm = () => {
            rmUploadForm.file = null;
            rmUploadForm.title = '';
            rmUploadForm.categoryId = null;
            rmUploadForm.description = '';
            rmUploadForm.confidentialityLevel = 'INTERNAL';
            rmIsEdit.value = false;
            rmEditId.value = null;
        };

        const showRmUploadDialog = () => {
            resetRmUploadForm();
            if (researchCategories.value.length === 0) {
                loadResearchCategories();
            }
            rmUploadDialogVisible.value = true;
        };

        const showRmEditDialog = (row) => {
            rmIsEdit.value = true;
            rmEditId.value = row.id;
            rmUploadForm.file = null;
            rmUploadForm.title = row.title;
            rmUploadForm.categoryId = null;
            rmUploadForm.confidentialityLevel = row.confidentialityLevel || 'INTERNAL';
            // Find matching category by name
            const cat = researchCategories.value.find(c => c.name === row.categoryName);
            if (cat) rmUploadForm.categoryId = cat.id;
            rmUploadForm.description = '';
            // Load detail to get description
            api.get(`/research-materials/${row.id}`).then(res => {
                rmUploadForm.description = res.data.data.description || '';
            }).catch(() => {});
            rmUploadDialogVisible.value = true;
        };

        const showRmConfDialog = (row) => {
            currentRmForConf.value = row;
            rmConfForm.confidentialityLevel = row.confidentialityLevel || 'INTERNAL';
            rmConfDialogVisible.value = true;
        };

        const handleRmConfUpdate = async () => {
            if (!currentRmForConf.value) return;
            rmConfLoading.value = true;
            try {
                await api.put(`/research-materials/${currentRmForConf.value.id}`, {
                    confidentialityLevel: rmConfForm.confidentialityLevel,
                });
                ElementPlus.ElMessage.success('保密等级更新成功');
                rmConfDialogVisible.value = false;
                loadResearchMaterials();
            } catch (e) {
                const msg = e.response?.data?.message || '保密等级更新失败';
                ElementPlus.ElMessage.error(msg);
            } finally {
                rmConfLoading.value = false;
            }
        };

        // ===== Research Data (研发数据) 函数 =====

        const rdTypeLabel = (t) => {
            const map = { TEST_RECORD: '测试记录', DESIGN_PARAM: '设计参数', EXPERIMENT: '实验记录', FAILURE: '故障记录',
                          RISK: '风险管理', BIOCOMPAT: '生物相容性', SOFTWARE_VV: '软件验证', EMC_SAFETY: 'EMC/电气安全', CLINICAL: '临床评价',
                          VALIDATION: '验证/确认', MATERIAL: '物料/来料检验', STERILIZATION: '灭菌/包装/货架寿命', CHANGE: '变更/偏差/CAPA',
                          OTHER: '其他' };
            return map[t] || t;
        };
        const rdStatusLabel = (s) => {
            const map = { DRAFT: '草稿', IN_PROGRESS: '进行中', COMPLETED: '已完成', ARCHIVED: '已归档' };
            return map[s] || s;
        };
        const rdStatusTagType = (s) => {
            const map = { DRAFT: 'info', IN_PROGRESS: 'warning', COMPLETED: 'success', ARCHIVED: '' };
            return map[s] || 'info';
        };
        const rdAccessRoleLabel = (r) => {
            const map = { owner: '我的', admin: '管理员', leader: '部门负责人', viewer: '可见' };
            return map[r] || r;
        };
        const rdAccessRoleTagType = (r) => {
            const map = { owner: 'success', admin: 'danger', leader: 'primary', viewer: 'info' };
            return map[r] || 'info';
        };
        const rdExtraLabel = (key) => {
            const map = {
                testItem: '测试项', flowRate: '流速', medium: '介质', temperature: '温度',
                duration: '持续时间', measuredResult: '实测结果', specification: '规格/标准',
                passFail: '合格判定', testEquipment: '测试设备',
                paramName: '参数名', paramValue: '参数值', unit: '单位', version: '版本',
                changeReason: '变更原因',
                objective: '目的', method: '方法', parameters: '参数',
                observation: '观察现象', conclusion: '结论',
                phenomenon: '故障现象', rootCause: '根本原因', action: '处理措施',
                trackingNo: '跟踪号', resolvedAt: '解决日期',
                // RISK
                hazardType: '危害类型', failureMode: '故障模式', severity: '严重度S',
                occurrence: '发生度O', detection: '可探测度D', controlMeasure: '控制措施',
                residualRisk: '剩余风险', traceToDesign: '追溯需求',
                // BIOCOMPAT
                bioTestItem: '试验项目', material: '材料', extractCondition: '浸提条件',
                bioTestOrg: '试验机构', bioReportNo: '报告编号', bioTestResult: '试验结果', bioConclusion: '结论',
                // SOFTWARE_VV
                swVersion: '软件版本', safetyClass: '安全等级', testLevel: '测试层级',
                swTestResult: '测试结果', defectCount: '缺陷数', traceMatrix: '需求追溯', swTestReport: '测试报告',
                // EMC_SAFETY
                emcTestItem: '测试项', emcStandard: '依据标准', emcMeasured: '实测值',
                emcLimit: '限值', emcPassFail: '判定', emcEquipment: '测试设备', emcTestOrg: '检测机构',
                // CLINICAL
                evalPath: '评价路径', compareDevice: '对比器械', differenceAnalysis: '差异分析',
                literatureSummary: '文献综述', evalReportNo: '评价报告', clinicalConclusion: '结论',
                // VALIDATION
                validationType: '验证/确认类型', standard: '依据标准', scope: '验证范围/对象',
                acceptanceCriteria: '接收准则', samples: '样本/批次', protocolNo: '方案编号',
                reportNo: '报告编号', result: '验证结果', conclusion: '结论', reviewer: '审核人',
                approver: '批准人',
                // MATERIAL
                materialName: '物料名称', materialCode: '物料编码', supplier: '供应商',
                materialSpec: '物料规格', iqcItem: '检验项目', iqcStandard: '检验标准',
                sampleQty: '抽样数量', iqcResult: '检验结果', iqcReportNo: '检验报告编号',
                coaAvailable: '有无COA', storageCondition: '储存条件', expiryDate: '有效期',
                // STERILIZATION
                sterMethod: '灭菌方式', sterParameter: '灭菌参数', sterLoad: '装载方式',
                sterVerification: '验证类型', sterResult: '灭菌验证结果', packTestItem: '包装试验项目',
                packTestResult: '包装试验结果', shelfLife: '货架寿命(月)', agingType: '老化试验类型',
                agingPeriod: '老化周期', sterReportNo: '报告编号',
                // CHANGE
                changeType: '变更类型', changeNo: '变更/偏差/CAPA编号', changeReason: '变更原因/偏差描述',
                riskAssessment: '风险评估', impactScope: '影响范围', actionPlan: '处理措施/CAPA',
                implementedDate: '实施日期', effectVerify: '效果验证', changeApprover: '批准人',
            };
            return map[key] || key;
        };

        const loadResearchData = async () => {
            rdLoading.value = true;
            try {
                const params = {
                    page: rdCurrentPage.value - 1,
                    size: rdPageSize.value,
                    view: rdView.value,
                };
                if (rdSearchKeyword.value) params.keyword = rdSearchKeyword.value;
                if (rdCategoryFilter.value) params.categoryId = rdCategoryFilter.value;
                if (rdTypeFilter.value) params.recordType = rdTypeFilter.value;
                if (rdParamCategoryFilter.value) params.paramCategory = rdParamCategoryFilter.value;
                const res = await api.get('/research-data', { params });
                const page = res.data.data;
                researchDataList.value = page.content;
                rdTotal.value = page.totalElements;
            } catch (e) {
                ElementPlus.ElMessage.error('加载研发数据列表失败');
            } finally {
                rdLoading.value = false;
            }
        };

        // ===== Suppliers methods =====
        const loadSuppliers = async () => {
            supplierLoading.value = true;
            try {
                const params = {
                    page: supplierCurrentPage.value - 1,
                    size: supplierPageSize.value,
                    includeDisabled: true,
                };
                if (supplierSearchKeyword.value) params.keyword = supplierSearchKeyword.value;
                if (supplierCategoryFilter.value) params.category = supplierCategoryFilter.value;
                if (supplierQualificationFilter.value) params.qualificationStatus = supplierQualificationFilter.value;
                const res = await api.get('/suppliers', { params });
                const page = res.data.data;
                supplierList.value = page.content;
                supplierTotal.value = page.totalElements;
            } catch (e) {
                ElementPlus.ElMessage.error('加载供应商列表失败');
            } finally {
                supplierLoading.value = false;
            }
        };

        const loadEnabledSuppliers = async () => {
            try {
                const res = await api.get('/suppliers/enabled');
                enabledSuppliers.value = res.data.data;
            } catch (e) { /* ignore */ }
        };

        const supplierQualificationLabel = (status) => {
            const map = { QUALIFIED: '合格', PENDING: '待审核', SUSPENDED: '已暂停' };
            return map[status] || status;
        };
        const supplierQualificationTagType = (status) => {
            const map = { QUALIFIED: 'success', PENDING: 'warning', SUSPENDED: 'danger' };
            return map[status] || 'info';
        };

        const resetSupplierForm = () => {
            supplierForm.supplierCode = '';
            supplierForm.name = '';
            supplierForm.category = '';
            supplierForm.contact = '';
            supplierForm.phone = '';
            supplierForm.email = '';
            supplierForm.qualificationStatus = 'PENDING';
            supplierForm.qualityContactName = '';
            supplierForm.qualityContactPhone = '';
            supplierForm.enabled = true;
            supplierForm.optimisticLockVersion = null;
            supplierIsEdit.value = false;
            supplierEditId.value = null;
        };

        const showSupplierCreateDialog = () => {
            resetSupplierForm();
            supplierEditDialogVisible.value = true;
        };

        const showSupplierEditDialog = (row) => {
            resetSupplierForm();
            supplierIsEdit.value = true;
            supplierEditId.value = row.id;
            supplierForm.supplierCode = row.supplierCode;
            supplierForm.name = row.name;
            supplierForm.category = row.category;
            supplierForm.contact = row.contact;
            supplierForm.phone = row.phone;
            supplierForm.email = row.email;
            supplierForm.qualificationStatus = row.qualificationStatus;
            supplierForm.qualityContactName = row.qualityContactName;
            supplierForm.qualityContactPhone = row.qualityContactPhone;
            supplierForm.enabled = row.enabled;
            supplierEditDialogVisible.value = true;
        };

        const showSupplierDetailDialog = (row) => {
            supplierDetail.value = { ...row };
            supplierDetailDialogVisible.value = true;
        };

        const handleSupplierSubmit = async () => {
            supplierSubmitting.value = true;
            try {
                const payload = { ...supplierForm };
                if (supplierIsEdit.value) {
                    await api.put(`/suppliers/${supplierEditId.value}`, payload);
                    ElementPlus.ElMessage.success('更新成功');
                } else {
                    await api.post('/suppliers', payload);
                    ElementPlus.ElMessage.success('创建成功');
                }
                supplierEditDialogVisible.value = false;
                loadSuppliers();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '操作失败');
            } finally {
                supplierSubmitting.value = false;
            }
        };

        const handleSupplierDisable = async (row) => {
            try {
                await api.delete(`/suppliers/${row.id}`);
                ElementPlus.ElMessage.success('已停用');
                loadSuppliers();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '操作失败');
            }
        };

        const handleSupplierEnable = async (row) => {
            try {
                await api.put(`/suppliers/${row.id}/enable`);
                ElementPlus.ElMessage.success('已启用');
                loadSuppliers();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '操作失败');
            }
        };

        // ===== Commercial Records methods =====
        const loadCommercialRecords = async () => {
            crLoading.value = true;
            try {
                const params = {
                    page: crCurrentPage.value - 1,
                    size: crPageSize.value,
                    view: crView.value,
                };
                if (crSearchKeyword.value) params.keyword = crSearchKeyword.value;
                if (crSupplierFilter.value) params.supplierId = crSupplierFilter.value;
                const res = await api.get('/commercial-records', { params });
                const page = res.data.data;
                commercialRecordList.value = page.content;
                crTotal.value = page.totalElements;
            } catch (e) {
                ElementPlus.ElMessage.error('加载成本记录列表失败');
            } finally {
                crLoading.value = false;
            }
        };

        const resetCrForm = () => {
            crForm.supplierId = null;
            crForm.itemName = '';
            crForm.costPrice = null;
            crForm.currency = 'CNY';
            crForm.effectiveDate = '';
            crForm.confidentialityLevel = 'CONFIDENTIAL';
            crForm.description = '';
            crForm.optimisticLockVersion = null;
            crIsEdit.value = false;
            crEditId.value = null;
        };

        const showCrCreateDialog = () => {
            resetCrForm();
            if (enabledSuppliers.value.length === 0) {
                loadEnabledSuppliers();
            }
            crEditDialogVisible.value = true;
        };

        const showCrEditDialog = (row) => {
            resetCrForm();
            crIsEdit.value = true;
            crEditId.value = row.id;
            crForm.supplierId = row.supplierId;
            crForm.itemName = row.itemName;
            crForm.costPrice = row.costPrice;
            crForm.currency = row.currency;
            crForm.effectiveDate = row.effectiveDate;
            crForm.confidentialityLevel = row.confidentialityLevel;
            // description 需要从 detail API 获取（listDto 不含 description）
            crEditDialogVisible.value = true;
            // 异步加载详情以填充 description
            api.get(`/commercial-records/${row.id}`).then(res => {
                crForm.description = res.data.data.description || '';
                crForm.optimisticLockVersion = res.data.data.optimisticLockVersion;
            }).catch(() => {});
        };

        const showCrDetailDialog = async (row) => {
            try {
                const res = await api.get(`/commercial-records/${row.id}`);
                crDetail.value = res.data.data;
                crDetailDialogVisible.value = true;
            } catch (e) {
                ElementPlus.ElMessage.error('加载详情失败');
            }
        };

        const handleCrSubmit = async () => {
            crSubmitting.value = true;
            try {
                const payload = { ...crForm };
                if (payload.costPrice !== null) payload.costPrice = Number(payload.costPrice);
                if (crIsEdit.value) {
                    await api.put(`/commercial-records/${crEditId.value}`, payload);
                    ElementPlus.ElMessage.success('更新成功');
                } else {
                    await api.post('/commercial-records', payload);
                    ElementPlus.ElMessage.success('创建成功');
                }
                crEditDialogVisible.value = false;
                loadCommercialRecords();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '操作失败');
            } finally {
                crSubmitting.value = false;
            }
        };

        const handleCrDelete = async (row) => {
            try {
                await api.delete(`/commercial-records/${row.id}`);
                ElementPlus.ElMessage.success('删除成功');
                loadCommercialRecords();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '删除失败');
            }
        };

        const resetRdForm = () => {
            rdForm.recordType = 'TEST_RECORD';
            rdForm.recordNo = ''; rdForm.title = ''; rdForm.recordDate = '';
            rdForm.operator = ''; rdForm.status = 'DRAFT';
            rdForm.deviceModel = ''; rdForm.batchNo = '';
            rdForm.confidentialityLevel = 'INTERNAL';
            rdForm.categoryId = null; rdForm.description = '';
            rdForm.testItem=''; rdForm.flowRate=''; rdForm.medium=''; rdForm.temperature=''; rdForm.duration='';
            rdForm.measuredResult=''; rdForm.testSpec=''; rdForm.passFail=''; rdForm.testEquipment='';
            rdForm.paramName=''; rdForm.paramValue=''; rdForm.unit=''; rdForm.dpSpec=''; rdForm.dpVersion=''; rdForm.changeReason='';
            rdForm.objective=''; rdForm.method=''; rdForm.expParams=''; rdForm.observation=''; rdForm.conclusion='';
            rdForm.phenomenon=''; rdForm.rootCause=''; rdForm.failAction=''; rdForm.trackingNo=''; rdForm.resolvedAt='';
            // RISK 重置
            rdForm.hazardType=''; rdForm.failureMode=''; rdForm.severity=null; rdForm.occurrence=null; rdForm.detection=null;
            rdForm.controlMeasure=''; rdForm.residualRisk=''; rdForm.traceToDesign='';
            // BIOCOMPAT 重置
            rdForm.bioTestItem=''; rdForm.material=''; rdForm.extractCondition=''; rdForm.bioTestOrg=''; rdForm.bioReportNo='';
            rdForm.bioTestResult=''; rdForm.bioConclusion='';
            // SOFTWARE_VV 重置
            rdForm.swVersion=''; rdForm.safetyClass=''; rdForm.testLevel=''; rdForm.swTestResult=''; rdForm.defectCount=null;
            rdForm.traceMatrix=''; rdForm.swTestReport='';
            // EMC_SAFETY 重置
            rdForm.emcTestItem=''; rdForm.emcStandard=''; rdForm.emcMeasured=''; rdForm.emcLimit=''; rdForm.emcPassFail='';
            rdForm.emcEquipment=''; rdForm.emcTestOrg='';
            // CLINICAL 重置
            rdForm.evalPath=''; rdForm.compareDevice=''; rdForm.differenceAnalysis=''; rdForm.literatureSummary='';
            rdForm.evalReportNo=''; rdForm.clinicalConclusion='';
            // VALIDATION 重置
            rdForm.validationType=''; rdForm.vStandard=''; rdForm.vScope=''; rdForm.acceptanceCriteria='';
            rdForm.vSamples=''; rdForm.vProtocolNo=''; rdForm.vReportNo=''; rdForm.vResult=''; rdForm.vConclusion='';
            rdForm.vReviewer=''; rdForm.vApprover='';
            // MATERIAL 重置
            rdForm.materialName=''; rdForm.materialCode=''; rdForm.materialSupplier=''; rdForm.materialSpec='';
            rdForm.iqcItem=''; rdForm.iqcStandard=''; rdForm.sampleQty=''; rdForm.iqcResult=''; rdForm.iqcReportNo='';
            rdForm.coaAvailable=''; rdForm.storageCondition=''; rdForm.materialExpiry='';
            // STERILIZATION 重置
            rdForm.sterMethod=''; rdForm.sterParameter=''; rdForm.sterLoad=''; rdForm.sterVerification='';
            rdForm.sterResult=''; rdForm.packTestItem=''; rdForm.packTestResult=''; rdForm.shelfLife='';
            rdForm.agingType=''; rdForm.agingPeriod=''; rdForm.sterReportNo='';
            // CHANGE 重置
            rdForm.changeType=''; rdForm.changeNo=''; rdForm.changeReason=''; rdForm.riskAssessment='';
            rdForm.impactScope=''; rdForm.actionPlan=''; rdForm.changeDate=''; rdForm.effectVerify=''; rdForm.changeApprover='';
            // OTHER 动态字段重置
            rdForm.dynamicFields = [];
            rdIsEdit.value = false;
            rdEditId.value = null;
        };

        const buildExtraDataFromForm = () => {
            const t = rdForm.recordType;
            if (t === 'TEST_RECORD') {
                return {
                    testItem: rdForm.testItem || null,
                    testConditions: {
                        flowRate: rdForm.flowRate || null,
                        medium: rdForm.medium || null,
                        temperature: rdForm.temperature || null,
                        duration: rdForm.duration || null,
                    },
                    measuredResult: rdForm.measuredResult || null,
                    specification: rdForm.testSpec || null,
                    passFail: rdForm.passFail || null,
                    testEquipment: rdForm.testEquipment || null,
                };
            }
            if (t === 'DESIGN_PARAM') {
                return {
                    paramName: rdForm.paramName || null,
                    paramValue: rdForm.paramValue || null,
                    unit: rdForm.unit || null,
                    specification: rdForm.dpSpec || null,
                    version: rdForm.dpVersion || null,
                    changeReason: rdForm.changeReason || null,
                };
            }
            if (t === 'EXPERIMENT') {
                return {
                    objective: rdForm.objective || null,
                    method: rdForm.method || null,
                    parameters: rdForm.expParams || null,
                    observation: rdForm.observation || null,
                    conclusion: rdForm.conclusion || null,
                };
            }
            if (t === 'FAILURE') {
                return {
                    phenomenon: rdForm.phenomenon || null,
                    rootCause: rdForm.rootCause || null,
                    action: rdForm.failAction || null,
                    trackingNo: rdForm.trackingNo || null,
                    resolvedAt: rdForm.resolvedAt || null,
                };
            }
            if (t === 'RISK') {
                return {
                    hazardType: rdForm.hazardType || null,
                    failureMode: rdForm.failureMode || null,
                    severity: rdForm.severity,
                    occurrence: rdForm.occurrence,
                    detection: rdForm.detection,
                    rpn: (rdForm.severity && rdForm.occurrence && rdForm.detection)
                        ? rdForm.severity * rdForm.occurrence * rdForm.detection : null,
                    controlMeasure: rdForm.controlMeasure || null,
                    residualRisk: rdForm.residualRisk || null,
                    traceToDesign: rdForm.traceToDesign || null,
                };
            }
            if (t === 'BIOCOMPAT') {
                return {
                    bioTestItem: rdForm.bioTestItem || null,
                    material: rdForm.material || null,
                    extractCondition: rdForm.extractCondition || null,
                    bioTestOrg: rdForm.bioTestOrg || null,
                    bioReportNo: rdForm.bioReportNo || null,
                    bioTestResult: rdForm.bioTestResult || null,
                    bioConclusion: rdForm.bioConclusion || null,
                };
            }
            if (t === 'SOFTWARE_VV') {
                return {
                    swVersion: rdForm.swVersion || null,
                    safetyClass: rdForm.safetyClass || null,
                    testLevel: rdForm.testLevel || null,
                    swTestResult: rdForm.swTestResult || null,
                    defectCount: rdForm.defectCount,
                    traceMatrix: rdForm.traceMatrix || null,
                    swTestReport: rdForm.swTestReport || null,
                };
            }
            if (t === 'EMC_SAFETY') {
                return {
                    emcTestItem: rdForm.emcTestItem || null,
                    emcStandard: rdForm.emcStandard || null,
                    emcMeasured: rdForm.emcMeasured || null,
                    emcLimit: rdForm.emcLimit || null,
                    emcPassFail: rdForm.emcPassFail || null,
                    emcEquipment: rdForm.emcEquipment || null,
                    emcTestOrg: rdForm.emcTestOrg || null,
                };
            }
            if (t === 'CLINICAL') {
                return {
                    evalPath: rdForm.evalPath || null,
                    compareDevice: rdForm.compareDevice || null,
                    differenceAnalysis: rdForm.differenceAnalysis || null,
                    literatureSummary: rdForm.literatureSummary || null,
                    evalReportNo: rdForm.evalReportNo || null,
                    clinicalConclusion: rdForm.clinicalConclusion || null,
                };
            }
            if (t === 'VALIDATION') {
                return {
                    validationType: rdForm.validationType || null,
                    standard: rdForm.vStandard || null,
                    scope: rdForm.vScope || null,
                    acceptanceCriteria: rdForm.acceptanceCriteria || null,
                    samples: rdForm.vSamples || null,
                    protocolNo: rdForm.vProtocolNo || null,
                    reportNo: rdForm.vReportNo || null,
                    result: rdForm.vResult || null,
                    conclusion: rdForm.vConclusion || null,
                    reviewer: rdForm.vReviewer || null,
                    approver: rdForm.vApprover || null,
                };
            }
            if (t === 'MATERIAL') {
                return {
                    materialName: rdForm.materialName || null,
                    materialCode: rdForm.materialCode || null,
                    supplier: rdForm.materialSupplier || null,
                    materialSpec: rdForm.materialSpec || null,
                    iqcItem: rdForm.iqcItem || null,
                    iqcStandard: rdForm.iqcStandard || null,
                    sampleQty: rdForm.sampleQty || null,
                    iqcResult: rdForm.iqcResult || null,
                    iqcReportNo: rdForm.iqcReportNo || null,
                    coaAvailable: rdForm.coaAvailable || null,
                    storageCondition: rdForm.storageCondition || null,
                    expiryDate: rdForm.materialExpiry || null,
                };
            }
            if (t === 'STERILIZATION') {
                return {
                    sterMethod: rdForm.sterMethod || null,
                    sterParameter: rdForm.sterParameter || null,
                    sterLoad: rdForm.sterLoad || null,
                    sterVerification: rdForm.sterVerification || null,
                    sterResult: rdForm.sterResult || null,
                    packTestItem: rdForm.packTestItem || null,
                    packTestResult: rdForm.packTestResult || null,
                    shelfLife: rdForm.shelfLife || null,
                    agingType: rdForm.agingType || null,
                    agingPeriod: rdForm.agingPeriod || null,
                    sterReportNo: rdForm.sterReportNo || null,
                };
            }
            if (t === 'CHANGE') {
                return {
                    changeType: rdForm.changeType || null,
                    changeNo: rdForm.changeNo || null,
                    changeReason: rdForm.changeReason || null,
                    riskAssessment: rdForm.riskAssessment || null,
                    impactScope: rdForm.impactScope || null,
                    actionPlan: rdForm.actionPlan || null,
                    implementedDate: rdForm.changeDate || null,
                    effectVerify: rdForm.effectVerify || null,
                    changeApprover: rdForm.changeApprover || null,
                };
            }
            if (t === 'OTHER') {
                // OTHER：动态自定义字段（键值对数组 -> 扁平对象）
                const obj = {};
                (rdForm.dynamicFields || []).forEach(f => {
                    if (f && f.key && String(f.key).trim()) {
                        obj[f.key.trim()] = (f.value !== undefined && f.value !== null) ? String(f.value) : null;
                    }
                });
                return Object.keys(obj).length > 0 ? obj : {};
            }
            return {};
        };

        const populateFormFromExtraData = (extra) => {
            if (!extra) return;
            if (rdForm.recordType === 'TEST_RECORD') {
                rdForm.testItem = extra.testItem || '';
                rdForm.flowRate = extra.testConditions?.flowRate || '';
                rdForm.medium = extra.testConditions?.medium || '';
                rdForm.temperature = extra.testConditions?.temperature || '';
                rdForm.duration = extra.testConditions?.duration || '';
                rdForm.measuredResult = extra.measuredResult || '';
                rdForm.testSpec = extra.specification || '';
                rdForm.passFail = extra.passFail || '';
                rdForm.testEquipment = extra.testEquipment || '';
            } else if (rdForm.recordType === 'DESIGN_PARAM') {
                rdForm.paramName = extra.paramName || '';
                rdForm.paramValue = extra.paramValue || '';
                rdForm.unit = extra.unit || '';
                rdForm.dpSpec = extra.specification || '';
                rdForm.dpVersion = extra.version || '';
                rdForm.changeReason = extra.changeReason || '';
            } else if (rdForm.recordType === 'EXPERIMENT') {
                rdForm.objective = extra.objective || '';
                rdForm.method = extra.method || '';
                rdForm.expParams = extra.parameters || '';
                rdForm.observation = extra.observation || '';
                rdForm.conclusion = extra.conclusion || '';
            } else if (rdForm.recordType === 'FAILURE') {
                rdForm.phenomenon = extra.phenomenon || '';
                rdForm.rootCause = extra.rootCause || '';
                rdForm.failAction = extra.action || '';
                rdForm.trackingNo = extra.trackingNo || '';
                rdForm.resolvedAt = extra.resolvedAt || '';
            } else if (rdForm.recordType === 'RISK') {
                rdForm.hazardType = extra.hazardType || '';
                rdForm.failureMode = extra.failureMode || '';
                rdForm.severity = extra.severity ?? null;
                rdForm.occurrence = extra.occurrence ?? null;
                rdForm.detection = extra.detection ?? null;
                rdForm.controlMeasure = extra.controlMeasure || '';
                rdForm.residualRisk = extra.residualRisk || '';
                rdForm.traceToDesign = extra.traceToDesign || '';
            } else if (rdForm.recordType === 'BIOCOMPAT') {
                rdForm.bioTestItem = extra.bioTestItem || '';
                rdForm.material = extra.material || '';
                rdForm.extractCondition = extra.extractCondition || '';
                rdForm.bioTestOrg = extra.bioTestOrg || '';
                rdForm.bioReportNo = extra.bioReportNo || '';
                rdForm.bioTestResult = extra.bioTestResult || '';
                rdForm.bioConclusion = extra.bioConclusion || '';
            } else if (rdForm.recordType === 'SOFTWARE_VV') {
                rdForm.swVersion = extra.swVersion || '';
                rdForm.safetyClass = extra.safetyClass || '';
                rdForm.testLevel = extra.testLevel || '';
                rdForm.swTestResult = extra.swTestResult || '';
                rdForm.defectCount = extra.defectCount ?? null;
                rdForm.traceMatrix = extra.traceMatrix || '';
                rdForm.swTestReport = extra.swTestReport || '';
            } else if (rdForm.recordType === 'EMC_SAFETY') {
                rdForm.emcTestItem = extra.emcTestItem || '';
                rdForm.emcStandard = extra.emcStandard || '';
                rdForm.emcMeasured = extra.emcMeasured || '';
                rdForm.emcLimit = extra.emcLimit || '';
                rdForm.emcPassFail = extra.emcPassFail || '';
                rdForm.emcEquipment = extra.emcEquipment || '';
                rdForm.emcTestOrg = extra.emcTestOrg || '';
            } else if (rdForm.recordType === 'CLINICAL') {
                rdForm.evalPath = extra.evalPath || '';
                rdForm.compareDevice = extra.compareDevice || '';
                rdForm.differenceAnalysis = extra.differenceAnalysis || '';
                rdForm.literatureSummary = extra.literatureSummary || '';
                rdForm.evalReportNo = extra.evalReportNo || '';
                rdForm.clinicalConclusion = extra.clinicalConclusion || '';
            } else if (rdForm.recordType === 'VALIDATION') {
                rdForm.validationType = extra.validationType || '';
                rdForm.vStandard = extra.standard || '';
                rdForm.vScope = extra.scope || '';
                rdForm.acceptanceCriteria = extra.acceptanceCriteria || '';
                rdForm.vSamples = extra.samples || '';
                rdForm.vProtocolNo = extra.protocolNo || '';
                rdForm.vReportNo = extra.reportNo || '';
                rdForm.vResult = extra.result || '';
                rdForm.vConclusion = extra.conclusion || '';
                rdForm.vReviewer = extra.reviewer || '';
                rdForm.vApprover = extra.approver || '';
            } else if (rdForm.recordType === 'MATERIAL') {
                rdForm.materialName = extra.materialName || '';
                rdForm.materialCode = extra.materialCode || '';
                rdForm.materialSupplier = extra.supplier || '';
                rdForm.materialSpec = extra.materialSpec || '';
                rdForm.iqcItem = extra.iqcItem || '';
                rdForm.iqcStandard = extra.iqcStandard || '';
                rdForm.sampleQty = extra.sampleQty || '';
                rdForm.iqcResult = extra.iqcResult || '';
                rdForm.iqcReportNo = extra.iqcReportNo || '';
                rdForm.coaAvailable = extra.coaAvailable || '';
                rdForm.storageCondition = extra.storageCondition || '';
                rdForm.materialExpiry = extra.expiryDate || '';
            } else if (rdForm.recordType === 'STERILIZATION') {
                rdForm.sterMethod = extra.sterMethod || '';
                rdForm.sterParameter = extra.sterParameter || '';
                rdForm.sterLoad = extra.sterLoad || '';
                rdForm.sterVerification = extra.sterVerification || '';
                rdForm.sterResult = extra.sterResult || '';
                rdForm.packTestItem = extra.packTestItem || '';
                rdForm.packTestResult = extra.packTestResult || '';
                rdForm.shelfLife = extra.shelfLife || '';
                rdForm.agingType = extra.agingType || '';
                rdForm.agingPeriod = extra.agingPeriod || '';
                rdForm.sterReportNo = extra.sterReportNo || '';
            } else if (rdForm.recordType === 'CHANGE') {
                rdForm.changeType = extra.changeType || '';
                rdForm.changeNo = extra.changeNo || '';
                rdForm.changeReason = extra.changeReason || '';
                rdForm.riskAssessment = extra.riskAssessment || '';
                rdForm.impactScope = extra.impactScope || '';
                rdForm.actionPlan = extra.actionPlan || '';
                rdForm.changeDate = extra.implementedDate || '';
                rdForm.effectVerify = extra.effectVerify || '';
                rdForm.changeApprover = extra.changeApprover || '';
            } else if (rdForm.recordType === 'OTHER') {
                // OTHER：扁平键值对 -> 动态字段数组（排除注入的 paramCategory 等内部字段）
                rdForm.dynamicFields = Object.keys(extra)
                    .filter(k => k !== 'paramCategory')
                    .map(k => ({ key: k, value: extra[k] !== null && extra[k] !== undefined ? String(extra[k]) : '' }));
            }
        };

        const showRdCreateDialog = () => {
            resetRdForm();
            if (researchCategories.value.length === 0) {
                loadResearchCategories();
            }
            rdEditDialogVisible.value = true;
        };

        const showRdEditDialog = async (row) => {
            rdIsEdit.value = true;
            rdEditId.value = row.id;
            if (researchCategories.value.length === 0) {
                loadResearchCategories();
            }
            try {
                const res = await api.get(`/research-data/${row.id}`);
                const d = res.data.data;
                rdForm.recordType = d.recordType || 'TEST_RECORD';
                rdForm.recordNo = d.recordNo || '';
                rdForm.title = d.title || '';
                rdForm.recordDate = d.recordDate || '';
                rdForm.operator = d.operator || '';
                rdForm.status = d.status || 'DRAFT';
                rdForm.deviceModel = d.deviceModel || '';
                rdForm.batchNo = d.batchNo || '';
                rdForm.confidentialityLevel = d.confidentialityLevel || 'INTERNAL';
                rdForm.categoryId = d.categoryId || null;
                rdForm.description = d.description || '';
                populateFormFromExtraData(d.extraData);
            } catch (e) {
                ElementPlus.ElMessage.error('加载详情失败');
                return;
            }
            rdEditDialogVisible.value = true;
        };

        const showRdDetailDialog = async (row) => {
            try {
                const res = await api.get(`/research-data/${row.id}`);
                currentRdDetail.value = res.data.data;
                rdDetailDialogVisible.value = true;
            } catch (e) {
                ElementPlus.ElMessage.error('加载详情失败');
            }
        };

        const showRdConfDialog = (row) => {
            currentRdForConf.value = row;
            rdConfForm.confidentialityLevel = row.confidentialityLevel || 'INTERNAL';
            rdConfDialogVisible.value = true;
        };

        const handleRdSave = async () => {
            if (!rdForm.recordType) {
                ElementPlus.ElMessage.warning('请选择记录类型');
                return;
            }
            if (!rdForm.title) {
                ElementPlus.ElMessage.warning('请输入标题');
                return;
            }
            rdEditLoading.value = true;
            try {
                const payload = {
                    recordType: rdForm.recordType,
                    recordNo: rdForm.recordNo || null,
                    title: rdForm.title,
                    recordDate: rdForm.recordDate || null,
                    operator: rdForm.operator || null,
                    status: rdForm.status,
                    deviceModel: rdForm.deviceModel || null,
                    batchNo: rdForm.batchNo || null,
                    confidentialityLevel: rdForm.confidentialityLevel,
                    categoryId: rdForm.categoryId || null,
                    description: rdForm.description || null,
                    extraData: buildExtraDataFromForm(),
                };
                if (rdIsEdit.value) {
                    await api.put(`/research-data/${rdEditId.value}`, payload);
                    ElementPlus.ElMessage.success('更新成功');
                } else {
                    await api.post('/research-data', payload);
                    ElementPlus.ElMessage.success('创建成功');
                }
                rdEditDialogVisible.value = false;
                loadResearchData();
            } catch (e) {
                const msg = e.response?.data?.message || '保存失败';
                ElementPlus.ElMessage.error(msg);
            } finally {
                rdEditLoading.value = false;
            }
        };

        const handleRdDelete = async (row) => {
            try {
                await api.delete(`/research-data/${row.id}`);
                ElementPlus.ElMessage.success('删除成功');
                loadResearchData();
            } catch (e) {
                const msg = e.response?.data?.message || '删除失败';
                ElementPlus.ElMessage.error(msg);
            }
        };

        const handleRdConfUpdate = async () => {
            if (!currentRdForConf.value) return;
            rdConfLoading.value = true;
            try {
                await api.put(`/research-data/${currentRdForConf.value.id}`, {
                    confidentialityLevel: rdConfForm.confidentialityLevel,
                });
                ElementPlus.ElMessage.success('保密等级更新成功');
                rdConfDialogVisible.value = false;
                loadResearchData();
            } catch (e) {
                const msg = e.response?.data?.message || '保密等级更新失败';
                ElementPlus.ElMessage.error(msg);
            } finally {
                rdConfLoading.value = false;
            }
        };

        const handleRmUpload = async () => {
            if (!rmIsEdit.value && !rmUploadForm.file) {
                ElementPlus.ElMessage.warning('请选择文件');
                return;
            }
            if (!rmUploadForm.title) {
                ElementPlus.ElMessage.warning('请输入资料标题');
                return;
            }
            if (!rmUploadForm.categoryId) {
                ElementPlus.ElMessage.warning('请选择资料分类');
                return;
            }
            if (!rmIsEdit.value && rmUploadForm.file.size > 50 * 1024 * 1024) {
                ElementPlus.ElMessage.error('文件大小不能超过 50 MB');
                return;
            }

            rmUploadLoading.value = true;
            try {
                if (rmIsEdit.value) {
                    await api.put(`/research-materials/${rmEditId.value}`, {
                        title: rmUploadForm.title,
                        categoryId: rmUploadForm.categoryId,
                        description: rmUploadForm.description || null,
                        confidentialityLevel: rmUploadForm.confidentialityLevel,
                    });
                    ElementPlus.ElMessage.success('更新成功');
                } else {
                    const formData = new FormData();
                    formData.append('file', rmUploadForm.file);
                    formData.append('title', rmUploadForm.title);
                    formData.append('categoryId', rmUploadForm.categoryId);
                    formData.append('description', rmUploadForm.description || '');
                    formData.append('confidentialityLevel', rmUploadForm.confidentialityLevel);
                    await api.post('/research-materials/upload', formData, {
                        headers: { 'Content-Type': 'multipart/form-data' },
                    });
                    ElementPlus.ElMessage.success('上传成功');
                }
                rmUploadDialogVisible.value = false;
                loadResearchMaterials();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '操作失败');
            } finally {
                rmUploadLoading.value = false;
            }
        };

        const handleRmDownload = async (row) => {
            try {
                const res = await fetch(`${API_BASE}/research-materials/${row.id}/download`, {
                    headers: { 'Authorization': `Bearer ${token.value}` },
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.message || `下载失败 (${res.status})`);
                }
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = row.fileName || row.title;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (e) {
                ElementPlus.ElMessage.error(e.message || '下载失败');
            }
        };

        const handleRmPreview = async (row) => {
            const ext = (row.fileExtension || '').toLowerCase();
            if (['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) {
                ElementPlus.ElMessage.info('Office 文档暂不支持在线预览，请下载查看');
                return;
            }
            if (!['pdf', 'jpg', 'jpeg', 'png', 'gif', 'txt', 'csv', 'md'].includes(ext)) {
                ElementPlus.ElMessage.warning('该文件类型不支持在线预览');
                return;
            }
            try {
                const res = await fetch(`${API_BASE}/research-materials/${row.id}/preview`, {
                    headers: { 'Authorization': `Bearer ${token.value}` },
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.message || `预览失败 (${res.status})`);
                }
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
                previewUrl.value = url;
                previewTitle.value = row.title;
                previewIsImage.value = ['jpg', 'jpeg', 'png', 'gif'].includes(ext);
                previewIsPdf.value = ext === 'pdf';
                previewIsOffice.value = false;
                previewDialogVisible.value = true;
            } catch (e) {
                ElementPlus.ElMessage.error(e.message || '预览失败');
            }
        };

        const handleRmDelete = async (row) => {
            try {
                await api.delete(`/research-materials/${row.id}`);
                ElementPlus.ElMessage.success('删除成功');
                loadResearchMaterials();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '删除失败');
            }
        };

        // ===== Share Management =====

        const showShareDialog = async (row) => {
            currentRmForShare.value = row;
            shareForm.userIds = [];
            shareList.value = [];
            shareDialogVisible.value = true;

            // Load shareable users (all employees except current user)
            try {
                const res = await api.get('/employees', { params: { page: 0, size: 1000 } });
                const page = res.data.data;
                shareableUsers.value = page.content.filter(u => u.realName !== currentUserName.value);
            } catch (e) {
                ElementPlus.ElMessage.error('加载用户列表失败');
            }

            // Load existing shares
            try {
                const res = await api.get(`/research-materials/${row.id}/shares`);
                shareList.value = res.data.data || [];
            } catch (e) { /* ignore */ }
        };

        const handleShare = async () => {
            if (!currentRmForShare.value) return;
            if (shareForm.userIds.length === 0) {
                ElementPlus.ElMessage.warning('请选择要分享的同事');
                return;
            }
            shareLoading.value = true;
            try {
                const res = await api.post(`/research-materials/${currentRmForShare.value.id}/share`, {
                    userIds: shareForm.userIds,
                });
                ElementPlus.ElMessage.success('分享成功');
                shareForm.userIds = [];
                // Refresh share list
                const sharesRes = await api.get(`/research-materials/${currentRmForShare.value.id}/shares`);
                shareList.value = sharesRes.data.data || [];
                loadResearchMaterials();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '分享失败');
            } finally {
                shareLoading.value = false;
            }
        };

        const handleUnshare = async (shareRow) => {
            if (!currentRmForShare.value) return;
            try {
                await api.delete(
                    `/research-materials/${currentRmForShare.value.id}/share/${shareRow.sharedWithUserId}`);
                ElementPlus.ElMessage.success('已取消分享');
                // Refresh share list
                const res = await api.get(`/research-materials/${currentRmForShare.value.id}/shares`);
                shareList.value = res.data.data || [];
                loadResearchMaterials();
            } catch (e) {
                ElementPlus.ElMessage.error(e.response?.data?.message || '取消分享失败');
            }
        };

        // ===== Menu =====
        const handleMenuSelect = (index) => {
            activeMenu.value = index;
            // AI 文档写作: 首次进入初始化 agent 视图（幂等；重复点击无副作用）
            if (index === 'agent-chat' && window.AgentChat) AgentChat.activate();
            if (index === 'employees') loadEmployees();
            if (index === 'dashboard') loadDashboard();
            if (index === 'departments') loadDepartments();
            if (index === 'documents') {
                loadCategories();
                loadDocuments();
            }
            if (index === 'research-materials') {
                loadResearchCategories();
                loadResearchMaterials();
            }
            if (index === 'research-data') {
                loadResearchCategories();
                loadResearchData();
            }
            if (index === 'suppliers') {
                loadSuppliers();
            }
            if (index === 'commercial-records') {
                loadEnabledSuppliers();
                loadCommercialRecords();
            }
        };

        // ===== Helpers =====
        const calcPercentage = (count, total) => {
            if (!total || total === 0) return 0;
            return Math.round((count / total) * 100);
        };
        const getBarColor = () => '#409eff';

        // ===== Init =====
        onMounted(() => {
            restoreSession();
            // 每 30 秒轮询未读通知数（顶栏角标实时性）
            notifTimer = setInterval(loadNotificationStats, 30000);
        });

        return {
            isLoggedIn, loginLoading, loginError, loginForm, loginRules,
            currentUserName, currentRole, currentRoleName,
            activeMenu, pageTitle, searchKeyword,
            filterDepartmentId, filterRoleCode, filterEnabled,
            // Notifications
            notifUnread, notifTodoCount, notifDrawerVisible, notifTab,
            notifTodos, notifList, notifTotal, notifPage, notifPageSize, notifLoading,
            announceDialogVisible, announceForm, announceSubmitting,
            openNotificationDrawer, handleNotifTabChange, handleNotifPageChange,
            handleNotificationClick, handleMarkAllRead,
            openAnnounceDialog, handlePublishAnnouncement,
            notifTypeTag, formatDateTime,
            dashboardStats, statCards,
            employeeList, tableLoading, currentPage, pageSize, totalEmployees,
            dialogVisible, dialogTitle, isEdit, submitLoading, empForm, empRules,
            departments, roles, showDeptDialog, deptForm,
            handleLogin, handleLogout, handleMenuSelect,
            loadEmployees, applyEmployeeFilter, showAddDialog, showEditDialog, handleSubmit, handleDelete,
            handleAddDept, calcPercentage, getBarColor, resetForm,
            // Department leader
            showLeaderDialog, leaderDialogDept, leaderForm, deptMembersForLeader,
            openLeaderDialog, handleSetLeader,
            // Confidentiality access
            showConfAccessDialog, confAccessTargetUser, confAccessList, confAccessForm,
            openConfAccessDialog, loadConfAccess, handleGrantConfAccess, handleRevokeConfAccess,
            handleToggleConfAccessMode,
            // Category access (researchCategories 复用研发资料模块的声明)
            showCategoryAccessDialog, categoryAccessTargetUser, categoryAccessList,
            categoryAccessSelectedIds, categoryAccessMode,
            openCategoryAccessDialog, loadCategoryAccess,
            handleGrantCategoryAccess, handleRevokeCategoryAccess, handleToggleCategoryAccessMode,
            // Document access (按资料授权)
            showDocumentAccessDialog, documentAccessTargetUser, documentAccessList,
            documentAccessForm, allResearchMaterials,
            openDocumentAccessDialog, loadAllResearchMaterials, loadDocumentAccess,
            handleGrantDocumentAccess, handleRevokeDocumentAccess,
            // Document management
            documentList, docLoading, docCurrentPage, docPageSize, docTotal,
            docSearchKeyword, docCategoryFilter, categories,
            uploadDialogVisible, uploadLoading, uploadForm,
            previewDialogVisible, previewUrl, previewTitle,
            previewIsImage, previewIsPdf, previewIsOffice,
            canUploadDoc, canDeleteDoc,
            loadDocuments, loadCategories, showUploadDialog, resetUploadForm,
            handleFileChange, handleUpload, handleDownload, handlePreview,
            closePreview, handleDeleteDoc,
            formatFileSize, visibilityLabel, visibilityTagType,
            // Document version control
            canPublishDoc, canRollbackDoc, canApproveDoc,
            publishDialogVisible, publishLoading, publishForm, currentDocForPublish,
            reviewDialogVisible, reviewLoading, reviewForm, currentDocForReview,
            revisionDialogVisible, revisionList, revisionLoading, currentDocForRevision,
            statusLabel, statusTagType,
            showPublishDialog, submitPublish, loadRevisions,
            handleRollback, handleDownloadRevision,
            // Document workflow (审批工作流)
            submitForReview, showReviewDialog, submitReviewDecision, retireDoc,
            // Research materials
            researchMaterialList, rmLoading, rmCurrentPage, rmPageSize, rmTotal,
            rmSearchKeyword, rmCategoryFilter, rmView, researchCategories,
            rmUploadDialogVisible, rmUploadLoading, rmIsEdit, rmUploadForm,
            shareDialogVisible, shareLoading, currentRmForShare, shareForm,
            shareableUsers, shareList,
            rmConfDialogVisible, rmConfLoading, currentRmForConf, rmConfForm,
            loadResearchMaterials, loadResearchCategories,
            showRmUploadDialog, showRmEditDialog, resetRmUploadForm,
            handleRmFileChange, handleRmUpload, handleRmDownload, handleRmPreview,
            handleRmDelete, accessRoleLabel, accessRoleTagType,
            confidentialityLabel, confidentialityTagType, accessModeLabel,
            showShareDialog, handleShare, handleUnshare,
            showRmConfDialog, handleRmConfUpdate,
            // Research data (研发数据)
            researchDataList, rdLoading, rdCurrentPage, rdPageSize, rdTotal,
            rdSearchKeyword, rdCategoryFilter, rdTypeFilter, rdParamCategoryFilter, rdView,
            rdEditDialogVisible, rdEditLoading, rdIsEdit, rdForm,
            rdConfDialogVisible, rdConfLoading, currentRdForConf, rdConfForm,
            rdDetailDialogVisible, currentRdDetail,
            loadResearchData, showRdCreateDialog, showRdEditDialog, showRdDetailDialog,
            showRdConfDialog, handleRdSave, handleRdDelete, handleRdConfUpdate,
            rdTypeLabel, rdStatusLabel, rdStatusTagType,
            rdAccessRoleLabel, rdAccessRoleTagType, rdExtraLabel,
            // Suppliers (供应商)
            supplierList, enabledSuppliers, supplierLoading,
            supplierCurrentPage, supplierPageSize, supplierTotal,
            supplierSearchKeyword, supplierCategoryFilter, supplierQualificationFilter,
            supplierEditDialogVisible, supplierDetailDialogVisible,
            supplierSubmitting, supplierIsEdit, supplierDetail, supplierForm, supplierRules,
            loadSuppliers, loadEnabledSuppliers,
            showSupplierCreateDialog, showSupplierEditDialog, showSupplierDetailDialog,
            handleSupplierSubmit, handleSupplierDisable, handleSupplierEnable,
            resetSupplierForm, supplierQualificationLabel, supplierQualificationTagType,
            // Commercial records (商业成本记录)
            commercialRecordList, crLoading, crCurrentPage, crPageSize, crTotal,
            crSearchKeyword, crSupplierFilter, crView,
            crEditDialogVisible, crDetailDialogVisible,
            crSubmitting, crIsEdit, crDetail, crForm, crRules,
            loadCommercialRecords, showCrCreateDialog, showCrEditDialog, showCrDetailDialog,
            handleCrSubmit, handleCrDelete, resetCrForm,
        };
    }
});

// Register Element Plus icons
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
}

app.use(ElementPlus);
app.mount('#app');
