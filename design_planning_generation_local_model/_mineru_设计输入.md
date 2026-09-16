

========== 第 1 页 ==========

<table><tr><td>文件类型Document Type</td><td>开发文档R&amp;D Document</td><td>保密密级Confidentiality</td><td colspan="2">机密Confidential</td></tr><tr><td>文件编号Document No.</td><td colspan="4">KF-CGM-2-0004</td></tr><tr><td>文件版本Document Version</td><td colspan="4">V7.0</td></tr><tr><td>适用范围Applicable Scope</td><td colspan="4">GS1</td></tr><tr><td colspan="5">设计输入</td></tr><tr><td colspan="5">相关文档Related Documents</td></tr><tr><td>文件编号Document No.</td><td colspan="3">文件名称Document Name</td><td>版本Version</td></tr><tr><td>KF-CGM-1-0001</td><td colspan="3">用户需求</td><td>6.0</td></tr><tr><td></td><td colspan="3"></td><td></td></tr><tr><td></td><td colspan="3"></td><td></td></tr><tr><td></td><td colspan="3"></td><td></td></tr><tr><td></td><td colspan="3"></td><td></td></tr><tr><td></td><td colspan="3"></td><td></td></tr><tr><td></td><td colspan="3"></td><td></td></tr><tr><td></td><td colspan="3"></td><td></td></tr><tr><td></td><td colspan="3"></td><td></td></tr></table>

<table><tr><td>编制人员</td><td>于政中</td><td>日期</td><td>2024.1.05</td></tr><tr><td>审核人员</td><td>陈志</td><td>日期</td><td>2024.01.05</td></tr><tr><td>批准人员</td><td>陈志政</td><td>日期</td><td>2024.01.05</td></tr></table>

========== 第 2 页 ==========

修订记录

Revision History

<table><tr><td>版本Version</td><td>ECN/PCN/CR</td><td>修订内容概述Description</td><td>修订人Revised By</td><td>生效日期Effective Date</td></tr><tr><td>1.0</td><td>/</td><td>创建Initial version</td><td>陈志</td><td>2018.03.14</td></tr><tr><td>2.0</td><td>/</td><td>使用新版本UI;</td><td>张瑾</td><td>2020.01.10</td></tr><tr><td>3.0</td><td>/</td><td>增加APP异常提示描述,存储7天、10天、14天监控数据</td><td>刘巧溪</td><td>2021.10.27</td></tr><tr><td>4.0</td><td>/</td><td>1、将“刺穿力&lt;1.2N”更正为“刺穿力&lt;3N。2、更正SR93、SR98法规年份。</td><td>龚明利</td><td>2023.07.05</td></tr><tr><td>5.0</td><td>/</td><td>1、新增加拿大、巴西、美国、澳大利亚国家的符合标准和法规清单2、更新国内法规3、更正3.0修订记录:更新欧盟法规</td><td>佘晓仪</td><td>2023.08.09</td></tr><tr><td>6.0</td><td>/</td><td>1、SR25将“电极厚度&lt;200μm”更正为“电极厚度&lt;300μm”2、SR25将“发射板尺寸&lt;30mm(L)*20mm(W)*10mm(H)重量&lt;50g”修改为“发射器尺寸&lt;35mm(L)*22mm(W)*6mm(H)重量&lt;50g”</td><td>佘晓仪</td><td>2023.12.25</td></tr><tr><td>7.0</td><td>CN2312015</td><td>1、传感器套装有效期由12个月更改为18个月;2、增加手表APP的输入需求。</td><td>于政中</td><td>2024.01.05</td></tr><tr><td></td><td></td><td></td><td></td><td></td></tr><tr><td></td><td></td><td></td><td></td><td></td></tr><tr><td></td><td></td><td></td><td></td><td></td></tr><tr><td></td><td></td><td></td><td></td><td></td></tr></table>

第1页共27页

========== 第 3 页 ==========

目录

目录....2

1. 介绍.... 4

1.1. 目的....4

1.2. 系统范围....4

1.3. 定义....4

1.4. 参考文档....4

2. 设计输入.... 5

2.1. 物理特性....5

2.2. 监测时间 5

2.3. 准确性....5

2.4. 一致性....5

2.5. 测量范围及线性 6

2.6. 响应时间....6

2.7. 植入后有效数据输出等待时间 6

2.8. 免指血校准....6

2.9. 抗干扰....6

2.10. 2.2.9.5 传感器外壳防护等级 6

2.11. 机械性能....6

2.12. 佩戴舒适性....7

2.13. 植入....7

2.14. 数据连接方式....8

2.15. 工作环境....8

2.16. 存储环境....8

2.17. 有效期....8

2.18. 数据与界面....8

2.19. 异常提示....9

2.20. 可操作性....9

2.21. 灭菌....10

2.22. 网络安全....10

2.23. 包装.... 10

2.24. 标贴....11

2.25. 随机文档....11

2.26. 法规、标准要求 12

2.26.1. 电气安全....12

2.26.2. 生物兼容性....12

第2页共27页

========== 第 4 页 ==========

2.26.3. 运输.... 12

2.26.4. EMC.... 13

2.27. 符合标准和法规清单....13

第3页共27页

========== 第 5 页 ==========

1. 介绍

1.1. 目的

本文对 GS1 型持续葡萄糖监测系统软件的需求规格进行定义。

1.2. 系统范围

持续葡萄糖监测系统软件，型号 GS1，包含传感器电极，发射器，助针器，读取器以及相关软件部分。

1.3. 定义

ID：需求唯一编号，每条需求对应一个ID。

SR: Specifications of Requirements, 需求规格。

1.4. 参考文档

KF-CGM-1-0001 用户需求

第4页共27页

========== 第 6 页 ==========

2. 设计输入

2.1. 物理特性

尺寸

ID: SR 1

传感器组件包尺寸不超过100mm（L）*100mm（W）*150mm（H）

ID : SR 2

敷贴器尺寸不超过 100mm（L）*100mm（W）*220mm（H）

ID: SR 3

读取器尺寸不超过 250mm（L）*100mm（W）*30mm（H）

重量

ID : SR 4

传感器组件包重量不得超过 200g

ID: SR 5

敷贴器重量不得超过 200g

ID: SR 6

发射器重量不得超过 50g

ID : SR 7

读取器重量不得超过 350g

2.2. 监测时间

ID: SR 8

使用时间达到 14*24 小时的连续监测葡萄糖水平

2.3. 准确性

ID: SR 9

2.2—3.9mmol/L ≤0.83 mmol/L

3.9—11.1mmol/L ≤12%

11.1—25.0mmol/L ≤20%

2.4. 一致性

ID: SR 10

批次间一致性差异系数在 \(5\%\) 以内

第5页共27页

========== 第 7 页 ==========

2.5. 测量范围及线性

ID: SR 11

产品检测葡萄糖的范围可以满足 2.2~25 mmol/L，线性  \( R^{2}>0.98 \)

2.6. 响应时间

ID: SR 12

当体外葡萄糖浓度变化时，传感器输出结果达到稳定所需的时间≤300s

2.7. 植入后有效数据输出等待时间

ID : SR 13

植入后有效数据输出等待时间小于等于1小时

2.8. 免指血校准

ID : SR 14

产品传感器中内置该批次反应酶与葡萄糖固定校准关系，使用时无需指血校准。

2.9. 抗干扰

ID : SR 15

产品传感器的测试结果误差≤±12%

明确主要干扰物情况，产品读数不受醋氨酚、布洛芬影响。但抗坏血酸、水杨酸等会干扰产品的准确性

2.10.2.2.9.5 传感器外壳防护等级

ID: SR 16

将发射器与传感电极组件组装为传感器后，传感器的外壳防护等级符合 GB/T4208-2017 标准中对防水等级 IP28 的规定。

2.11. 机械性能

ID: SR 17

产品部件及部件间机械性能较为稳固

ID: SR 18

产品的工作电极和参比电极连接牢固度大于 \(18\mathrm{g}\)

第6页共27页

========== 第 8 页 ==========

ID: SR 19

传感器机械要求，如电极连接牢固度、传感器与发射器间插入力（如适用）、导引针穿刺力（如适用）、导引针针座拉力、针座探头基座拔出力、贴片拉力、探头拉力、导引针回缩。

ID: SR 20

传感器与连接器、连接器底座应紧密连接无松动，电极能承受4N的拉力，连接器无松动或电极断裂

ID: SR 21

传感器旋转角度 \(\leqslant 45^{\circ}\) ，产品不会出现电极脱落现象，可以正常工作

持粘性

ID : SR 22

粘贴片的持粘性应符合YY/T0148—2017附录B中第B.2章

ID : SR 23

剥离强度

YY/T 0148—2017 附录 B 中第 B.3 章

2.12. 佩戴舒适性

胶带 舒适性

ID : SR 24

YY/T 0471.4—2018 可伸展性不大于 14N/cm，永久变形不大于 5%。

ID : SR 25

电极头部宽度 \(< 500\mu \mathrm{m}\) 厚度 \(< 300\mu \mathrm{m}\)

发射器尺寸 \(< 35\mathrm{mm}(\mathrm{L})^{*}22\mathrm{mm}(\mathrm{W})^{*}6\mathrm{mm}(\mathrm{H})\) 重量 \(< 50\mathrm{g}\) 表面，倒角处理，无批锋及毛刺

2.13. 植入

ID : SR 26

导引针（刺入皮肤）尺寸不超过 \(10\mathrm{mm}(\mathrm{L})^{*}1\mathrm{mm}(\mathrm{W})^{*}1\mathrm{mm}(\mathrm{H})\)

ID: SR 27

刺穿力 \(< 3.0\mathrm{N}\)

ID: SR 28

垂直刺入，扎针深度为<6mm，允许±15°偏差

ID : SR 29

产品敷贴器的发射压力 \(< 5\mathrm{N}\)

第7页共27页

========== 第 9 页 ==========

ID : SR 30

佩戴完导引针不能外露

2.14. 数据连接方式

ID : SR 31

发射器与读取器或者移动计算终端采用便利的连接方式，蓝牙无线连接，数据加密保护；持续葡萄糖监测系统软件、SIBIONICS、SIBIONICS GSW 可以通过 HTTPS 与云服务器通信。

2.15. 工作环境

ID : SR 32

传感器工作温度: \(5^{\circ} \mathrm{C}\) 至 \(40^{\circ} \mathrm{C}\)

ID: SR 33

读取器的使用环境温度：5℃至40℃且环境湿度：10%至90%RH

2.16. 存储环境

ID : SR 34

传感器的存贮温度可在 \(4^{\circ} \mathrm{C}\) 至 \(25^{\circ} \mathrm{C}\) 且环境湿度 \(10 \%\) 至 \(90 \% \mathrm{RH}\) 。

ID : SR 35

读取器符合 IEC60601-1-11 的要求，温度范围-20°C 至 60°C，湿度范围为 10-90%RH（非冷凝）

2.17. 有效期

ID: SR 36

产品有效期为 传感器套装 18 个月

读取器 3年

2.18. 数据与界面

ID : SR 37

产品提供数据主动读取显示功能，5分钟显示一笔血糖

ID : SR 38

读取器或者移动计算机终端 SIBIONICS 可以显示连续监测图谱，并且可以给出每天血糖数据最高葡萄糖值、最低葡萄糖值及葡萄糖值趋势图；持续葡萄糖监测系统软件需提供对血糖进行实时监测，可查看血糖分析、多日血糖叠加情况；可进行编辑资料、查看血糖报告、分享血糖数据，设置血糖显示的单位等功能；SIBIONICS GSW 可以显示连续监测图谱。

ID : SR 39

需要提供高低血糖提醒功能，高低血糖值、提醒方式等可根据用户需求设置

第8页共27页

========== 第 10 页 ==========

ID : SR 40

产品可以提供 AGP 报告（需要≥5 d 的监测数据才能形成）

ID : SR 41

可以存储 7 天、10 天、14 天监控数据，可显示每日血糖；可同步血糖数据至智能手表

ID: SR 42

其它：事件录入 产品有添加事件功能，可以实时添加运动，饮食，药品等信息

ID: SR 43

设置 可以清楚缓存、修改密码、导出用户操作日志、查看软件基本信息、服务协议、隐私政策、客服电话、退出登录等

ID: SR 44

电源键 长按操作可以进行屏幕息屏开关控制

ID: SR 45

触屏 屏幕支持 触控操作

2.19. 异常提示

ID : SR 46

连续 5 分钟读取器没有连接到 CGM，读取器会提示“CGM 信号丢失”，提醒用户重新尝试连接，点击确定，可清除提示；持续葡萄糖监测系统软件在设备连接情况有提示，若断开连接会有相关提示和操作，当传感器在可通讯范围内时，传感器自动再次连接。

ID : SR 47

连续 5 分钟发射板高于  \( 40^{\circ} \) C 或者低于  \( 20^{\circ} \) C，提示温度异常

ID : SR 48

根据电流异常算法的输出结果，提示传感器异常

ID: SR 49

传感器使用时间结束，读取器会有提醒；持续葡萄糖监测系统软件操作错误时、获取系统权限异常时、用户血糖异常时，弹出提示，必填项如果未填写相关信息，或者填写不符合规范，则弹出提示，二次确认提示；传感器使用时间结束，持续葡萄糖监测系统软件提醒“当前传感器已失效连接新传感器”。

2.20. 可操作性

ID : SR 50

1. 参考 YY/T 1474-2016 医疗器械 可用性工程对医疗器械的应用

2. 产品参照 IEC 60601-1-11:2015 家用医疗器械标准

第9页共27页

========== 第 11 页 ==========

ID : SR 51

产品中易触发装置位置处，需有防呆结构

ID : SR 52

当发射器与敷贴器结合时，可以听到明显的咔哒声，此时电极部分可以可靠地被敷贴器带出来

ID : SR 53

胶贴易撕把手

ID: SR 54

提供明确的标识

ID: SR 55

详细易懂的操作指引等

2.21. 灭菌

ID: SR 56

产品传感器套包进行灭菌包装设计，支持电子束灭菌方式，一次性使用，无菌保证水平要求达到 \(10^{-6}\) 。

2.22. 网络安全

ID: SR 57

无线传输数据保密及有效性

ID: SR 58

产品的一个传感器在和某个读取器连接后即绑定，不可再和其它读取器进行连接。同一时间一个读取器只能对应一个进行传感器工作，但断开连接后，此读取器可以连接其它传感器。

ID : SR 59

当5套产品系统近距离工作时，不会导致任何危险，数据不会相互串扰

ID: SR 60

符合《医疗器械网络安全注册技术审查指导原则》

2.23. 包装

ID: SR 61

传感器组件包采用铝箔包装

ID: SR 62

传感器套装采用纸盒包装，附带说明书

第10页共27页

========== 第 12 页 ==========

ID : SR 63

最后采用瓦楞纸箱包装

2.24. 标贴

ID : SR 64

产品标签包含安全标示，注意事项，使用时间

ID : SR 65

至少提供中国（简体中文）

ID : SR 66

主标贴中要有产品预期使用寿命的宣称。

ID : SR 67

需要提供主标贴，至少包含以下内容：产品名称、规格型号、序列号、公司信息；

ID : SR 68

电池标识标贴至少包含以下内容：产品名称、公司信息、规格信息、警告信息；需包括中文

ID: SR 69

主机上应有商标、机器名称标识

ID: SR 70

主机上应有输入/输出接口标识，AC 输入电压、频率和电流标识

ID : SR 71

主机上指示灯标识，包括开机状态灯、电池供电/充电灯、外部电源供电状态指示灯的标识

ID: SR 72

提示用户查阅手册标识

2.25. 随机文档

说明书

ID: SR 73

受检者希望产品说明书中包含检测原理，校准方法，有效时长，禁忌症，详细的使用指导，适用范围及条件，电磁兼容信息，家用情况说明

ID: SR 74

保修卡，合格证；

第11页共27页

========== 第 13 页 ==========

2.26. 法规、标准要求

2.26.1. 电气安全

根据 GB9706.1 安全分类

ID: SR 75

按防电击类型：Ⅱ类设备，带内部电源

D: SR 76

按防电击程度类型：BF型应用部分

ID : SR 77

进液防护等级：IP28

ID : SR 78

工作模式：连续工作

ID : SR 79

爆炸防护等级：

不提供爆炸防护（普通设备）

不适合在含有可燃性麻醉气体混合空气、氧气或笑气的环境中使用

ID : SR 80

安装使用方式:可携带式设备

2.26.2. 生物兼容性

ID: SR 81

应根据GB/T16886.1-2022（等同于ISO10993-1:2018）对持续葡萄糖监测系统预期和患者接触的设备部件和附件进行生物学评价，应提供合法的证明文件或进行生物学试验。

ID : SR 82

如需进行生物学试验，相关试验项目的试验要求如下：

- 细胞毒性试验：按照 GB/T 16886.5 的要求进行试验，标准要求：反应等级不大于 1（GB/T 16886.5）；

- 致敏试验：按照 GB/T 16886.10 要求进行试验，标准要求：对照组动物等级<1；

- 刺激试验：按照GB/T16886.10要求进行试验，标准要求：动物皮肤刺激试验原发性刺激指数（PII） \(\leqslant 0.4\) 。

2.26.3. 运输

ID : SR 83

符合 ISTA 运输测试程序 2A 堆码试验、振动试验和跌落试验的要求。

ISTA 2A：预处理试验，抗压试验，随机振动试验，自由跌落试验，随机振动试验。

第12页共27页

========== 第 14 页 ==========

ID: SR 84

符合 GB/T14710:2009 中关于运输试验的要求。

GB/T14710：三级公路，200km，40km/h

2.26.4. EMC

ID: SR 85

电磁发射水平应符合 GB 4824-2019 中 1 组 B 类的要求，分类如下：

辐射发射：GB 4824 中 Group1,Class B

传导发射：GB 4824 中 Group 1,Class B

ID: SR 86

抗扰度水平:

ESD 抗扰度符合 GB/T 17626.2 条款中：空气放电±8kV

射频辐射抗扰度满足 GB/T 17626.3 条款中：3V/m 80%AM@1kHz

工频磁场抗扰度符合 GB/T 17626.8 条款中：3A/m，50Hz、3A/m，60Hz

2.27. 符合标准和法规清单

ID : SR 87

YY/T 0316-2016 医疗器械风险管理对医疗器械的应用

ID : SR 88

GB/T 191-2008 包装储运图示标志

ID : SR 89

YY/T 0466.1-2009 医疗器械用于医疗器械标签、标记和提供信息的符号 第1部分：通用要求

ID : SR 90

YY/T 0466.2-2015 医疗器械 用于医疗器械标签、标记和提供信息的符号 第 2 部分: 符号的制订、选择和确认 (2016.6.1 起实施)

ID : SR 91

GB/T 9969-2008 工业产品使用说明书 总则

ID: SR 92

医疗器械说明书和标签管理规定（国家食品药品监督管理总局令第6号）

ID: SR 93

GB/T 14710-2009 医用电器环境要求及试验方法

ID: SR 94

GB/T 16886.1-2022 医疗器械生物学评价 第 1 部分：风险管理过程中的评价与试验

第13页共27页

========== 第 15 页 ==========

ID : SR 95

GB/T 16886.5-2017 医疗器械生物学评价 第 5: 部分体外细胞毒性试验

ID : SR 96

GB/T16886.10-2017医疗器械生物学评价 第10：部分刺激与迟发型超敏反应试验

ID : SR 97

GB 9706.1-2007 医用电气设备 第1部分：安全通用要求

GB 9706.15-2008 医用电气设备 第 1-1 部分：通用安全要求 并列标准：医用电气系统安全要求

ID : SR 98

GB/T 18455: 2022 包装回收标志

ID: SR 99

YY 0505-2012 医用电气设备 第 1-2 部分：安全通用要求 并列标准：电磁兼容 要求和试验

ID : SR 100

《移动医疗器械注册技术审查指导原则》

ID : SR 101

《医疗器械软件注册审查指导原则》

ID: SR 102

GB/T 25000.51-2016 《系统与软件工程 系统与软件质量要求和评价》

ID: SR 103

YY/T 0664-2020《医疗器械软件 软件生存周期过程》

ID : SR 104

GB 9706.1-2020《医用电气设备 第1部分：基本安全和基本性能的通用要求》

ID: SR 105

YY 9706.111-2021《医用电气设备 第1-11部分：基本安全和基本性能的通用要求 并列标准：在家庭护理环境中使用的医用电气设备和医用电气系统的要求》

ID: SR 106

YY 9706.102-2021《医用电气设备 第1-2部分：基本安全和基本性能的通用要求 并列标准：电磁兼容 要求和试验》

ID: SR 107

国内 GMP 适用法规识别:

《持续葡萄糖监测系统注册审查指导原则》

《医疗器械说明书和标签管理规定》

第14页共27页

========== 第 16 页 ==========

《药品医疗器械飞行检查办法》

《医疗器械分类规则》

《医疗器械通用名称命名规则》

《医疗器械不良事件监测和再评价管理办法》

《国家药监局关于发布医疗器械唯一标识系统规则的公告》

《医疗器械生产质量管理规范》

《国家药监局关于医疗器械主文档登记事项的公告》

《医疗器械监督管理条例》

《医疗器械注册与备案管理办法》

《医疗器械网络安全注册审查指导原则》

《医疗器械生产监督管理办法》

《医疗器械临床试验质量管理规范》

《医疗器械生产监督管理办法》

《广东省医疗器械注册质量体系核查》

《医疗器械网络销售监督管理办法》

《医疗器械召回管理办法》

ID: SR 108

《国家药监局关于发布医疗器械安全和性能基本原则的通告》，具体详见《医疗器械安全有效基本要求清单》文档

ID: SR 109

MDR 适用标准、通用安全与性能要求检查，详见《TD-GS1-06 Applied standards and GSPR checklist》文档

ID: SR 110

GBT 42062-2022 医疗器械 风险管理对医疗器械的应用

ID: SR 111

ISO 14971:2019-Ed.3.0 Medical devices - Application of risk management to medical devices（加拿大）

ID: SR 112

ISO 14971:2019-Ed.3.0(ABNT NBR ISO 14971:2020 Versão Corrigida:2020) Medical devices - Application of risk management to medical devices (巴西)

ID: SR 113

ISO 14971:2019-Ed.3.0 Medical devices - Application of risk management to medical devices（美国）

ID: SR 114

ISO 14971:2019(AS ISO 14971:2020) Medical devices — Application of risk management to medical devices（澳大利亚）

ID: SR 115

ISO 15223-1:2021(ABNT NBR ISO 15223-1:2022) Medical devices - Symbols to be used with information to be supplied by the manufacturer（巴西）

第 15 页 共 27 页

========== 第 17 页 ==========

ID: SR 116

ISO 15223-1 Fourth edition 2021-07 Medical devices - Symbols to be used with information to be supplied by the manufacturer - Part 1: General requirements (美国)

ID: SR 117

ISO 15223-1:2021 Medical devices — Symbols to be used with information to be supplied by the manufacturer — Part 1: General requirements（澳大利亚）

ID: SR 118

ISO 10993-1:2018-Ed.5.0 Biological evaluation of medical devices - Part 1: Evaluation and testing within a risk management process (加拿大)

ID : SR 119

ISO 10993-1:2018(ABNT NBR ISO 10993-1:2022) Biological evaluation of medical devices — Part 1: Evaluation and testing within a risk management process (巴西)

ID : SR 120

ISO 10993-1 Fifth edition 2018-08 Biological evaluation of medical devices - Part 1: Evaluation and testing within a risk management process (美国)

ID : SR 121

ISO 10993-1:2018 Biological evaluation of medical devices — Part 1: Evaluation and testing within a risk management process（澳大利亚）

ID : SR 122

ISO 10993-5:2009-Ed.3.0 Biological evaluation of medical devices - Part 5: Tests for in vitro cytotoxicity (加拿大)

ID : SR 123

ISO 10993-5:2009 Biological evaluation of medical devices — Part 5: Tests for in vitro cytotoxicity (巴西)

ID : SR 124

ISO 10993-5 Third edition 2009-06-01 Biological evaluation of medical devices - Part 5: Tests for in vitro cytotoxicity (美国)

ID : SR 125

ISO 10993-5:2009 Biological evaluation of medical devices — Part 5: Tests for in vitro cytotoxicity (澳大利亚)

ID : SR 126

ISO 10993-10:2010-Ed.3.0 Biological evaluation of medical devices - Part 10: Tests for irritation and skin sensitization (加拿大)

第16页共27页

========== 第 18 页 ==========

ID: SR 127

ISO 10993-10:2021 Biological evaluation of medical devices — Part 10: Tests for skin sensitization (巴西)

ID: SR 128

ISO 10993-10 Fourth edition 2021-11 Biological evaluation of medical devices - Part 10: Tests for skin sensitization (美国)

ID: SR 129

ISO 10993-10:2021 Biological evaluation of medical devices — Part 10: Tests for irritation and skin sensitization (澳大利亚)

ID: SR 130

IEC 60601-1:2005-Ed.3.0(CAN/CSA C22.2 NO 60601-1:2014-Ed.3.0/IEC 60601-1:2012-Ed.3.1) Medical electrical equipment – Part 1: General requirements for basic safety and essential performance (加拿大)

ID: SR 131

IEC 60601-1:2005/COR3:2022(IEC 60601-1:2021/AMD1 / ABNT NBR IEC 60601-1:2010) Medical electrical equipment – Part 1: General requirements for basic safety and essential performance (巴西)

ID : SR 132

IEC 60601-1 Edition 3.2 2020-08 CONSOLIDATED VERSION Medical electrical equipment - Part 1: General requirements for basic safety and essential performance（美国）

ID: SR 133

IEC 60601-1:2005/COR3:2022 Medical electrical equipment - Part 1: General requirements for basic safety and essential performance (澳大利亚)

ID: SR 134

IEC 60601-1-2:2014-Ed.4.0 Medical electrical equipment – Part 1-2: General requirements for basic safety and essential performance – Collateral standard: Electromagnetic disturbances – Requirements and tests（加拿大）

ID: SR 135

IEC 60601-1-2:2014/AMD1:2020(ABNT NBR IEC 60601-1-2:2017) Medical electrical equipment – Part 1-2: General requirements for basic safety and essential performance – Collateral standard: Electromagnetic disturbances – Requirements and tests (巴西)

ID: SR 136

IEC 60601-1-2 Edition 4.1 2020-09 CONSOLIDATED VERSION Medical electrical equipment - Part 1-2: General requirements for basic safety and essential performance - Collateral Standard: Electromagnetic disturbances - Requirements and tests (美国)

ID: SR 137

第17页共27页

========== 第 19 页 ==========

IEC 60601-1-2:2014/AMD1:2020 Medical electrical equipment - Part 1-2: General requirements for basic safety and essential performance - Collateral Standard: Electromagnetic disturbances - Requirements and tests (澳大利亚)

ID: SR 138

IEC 62304:2015-Ed.1.1 Medical device software - Software life cycle processes（加拿大）

ID: SR 139

IEC 62304:2006/Amd 1:2015(ABNT NBR IEC 62304:2023) Medical device software — Software life cycle processes（巴西）

ID: SR 140

IEC 62304 Edition 1.1 2015-06 CONSOLIDATED VERSION Medical device software - Software life cycle processes（美国）

ID: SR 141

IEC 62304:2006+AMD1:2015 Medical device software - Software life-cycle processes（澳大利亚）

ID : SR 142

IEC 60601-1-11:2010 -Ed 1.0 Medical electrical equipment – Part 1-11: General requirements for basic safety and essential performance – Collateral Standard: Requirements for medical electrical equipment and medical electrical systems used in the home healthcare environment (加拿大)

ID : SR 143

IEC 60601-1-11:2015/Amd 1:2020(ABNT NBR IEC 60601-1-11:2021) Medical electrical equipment — Part 1-11: General requirements for basic safety and essential performance — Collateral standard: Requirements for medical electrical equipment and medical electrical systems used in the home healthcare environment — Amendment 1（巴西）

ID : SR 144

IEC 60601-1-11 Edition 2.1 2020-07 CONSOLIDATED VERSION Medical electrical equipment - Part 1-11: General requirements for basic safety and essential performance - Collateral Standard: Requirements for medical electrical equipment and medical electrical systems used in the home healthcare environment (美国)

ID : SR 145

IEC 60601-1-11:2015/Amd 1: 2020 Medical electrical equipment - Part 1-11: General requirements for basic safety and essential performance - Collateral standard: Requirements for medical electrical equipment and medical electrical systems used in the home healthcare environment (澳大利亚)

ID : SR 146

SOR/98-282 Canadian Medical Devices Regulations（加拿大）

ID: SR 147

ISO 13485:2016(CAN/CSA-ISO 13485:16) Medical Devices -- Quality management systems --

第18页共27页

========== 第 20 页 ==========

Requirements for regulatory purposes (加拿大)

ID : SR 148

ISO 15225:2016 Medical devices – Quality management – Medical device nomenclature data structure (加拿大)

ID : SR 149

IEC 60601-1-6:2013-Ed.3.1 Medical electrical equipment – Part 1-6: General requirements for basic safety and essential performance – Collateral standard: Usability（加拿大）

ID: SR 150

ISO 11137-1:2006-Ed.1.0 Sterilization of health care products - Radiation - Part 1: Requirement for development, validation and routine control of a sterilization process for medical devices (加拿大)

ID: SR 151

ISO 11137-2:2013-Ed.3.0 Sterilization of health care products - Radiation - Part 2: Establishing the sterilization dose（加拿大）

ID: SR 152

ISO 11607-1:2019-Ed.2.0 Packaging for terminally sterilized medical devices - Part 1: Requirements for materials, sterile barrier systems and packaging systems (加拿大)

ID : SR 153

ISO 11607-2:2019-Ed.2.0 Packaging for terminally sterilized medical devices - Part 2: Validation requirements for forming, sealing and assembly processes (加拿大)

ID: SR 154

ISO 11737-1:2018-Ed.3.0 Sterilization of medical devices - Microbiological methods - Part 1: Determination of population of microorganisms on products ISO 11737-1:2018-Ed.3.0/Amd.1:2021（加拿大）

ID: SR 155

ISO 10993-2:2006-Ed.2.0 Biological evaluation of medical devices - Part 2: Animal welfare requirements (加拿大)

ID: SR 156

ISO 10993-3:2014-Ed.3.0 Biological evaluation of medical devices - Part 3: Tests for genotoxicity, carcinogenicity and reproductive toxicity (加拿大)

ID: SR 157

ISO 10993-6:2016-Ed.3.0 Biological evaluation of medical devices - Part 6: Tests for local effects after implantation (加拿大)

ID: SR 158

ISO 10993-11:2017-Ed.3.0 Biological evaluation of medical devices - Part 11: Tests for systemic toxicity

第19页共27页

========== 第 21 页 ==========

(加拿大)

ID: SR 159

ISO 10993-12:2007-Ed.3.0 Biological evaluation of medical devices - Part 12: Sample preparation and reference materials (加拿大)

ID : SR 160

ISO 10993-18:2005-Ed.1.0 Biological evaluation of medical devices - Part 18: Chemical characterization of materials (加拿大)

ID: SR 161

IEC 62366-1:2015-Ed.1.0 Medical devices -Part 1: Application of usability engineering to medical devices  
IEC 62366-1:2015-Ed.1.0/COR 1:2016（加拿大）

ID: SR 162

ISO 15197:2013-Ed.2.0 In vitro diagnostic test systems – Requirements for blood-glucose monitoring systems for self-testing in managing diabetes mellitus (加拿大)

ID : SR 163

ASTM F1140-13 Standard Test Methods for Internal Pressurization Failure Resistance of Unrestrained Packages（加拿大）

ID: SR 164

ISO 14155:2020-Ed.3.0 Clinical investigation of medical devices for human subjects - Good clinical practice (加拿大)

ID: SR 165

ISO/TR 24971:2020 Medical devices — Guidance on the application of ISO 14971（加拿大）

ID: SR 166

IEC 82304-1:2016 Health software - Part 1: General requirements for product safety (加拿大)

ID: SR 167

ISO 20417:2021 Medical devices — Information to be supplied by the manufacturer（加拿大）

ID: SR 168

ISO 15223-1:2021 Medical devices — Symbols to be used with information to be supplied by the manufacturer — Part 1: General requirements（加拿大）

ID: SR 169

RDC No. 751/2022 Provides the rules on medical device notification and registration effective March 1, 2023. (巴西)

ID : SR 170

RDC No. 36/2015 Establishes general pre-market requirements for IVDs, including risk classification

第20页共27页

========== 第 22 页 ==========

rules, registration requirements, Technical Dossier, and labeling/IFU requirements. (巴西)

ID: SR 171

RDC No. 665/2022 Provides the current Good Manufacturing Practices (GMP) requirements for medical and IVDs (巴西)

ID: SR 172

RDC No. 657/2022 Provides the comprehensive regulatory requirements for software as a medical device (SaMD). (巴西)

ID: SR 173

RDC No. 546-2021 Establishes essential safety and efficacy requirements applicable to health products.
(巴西)

ID: SR 174

ISO 13485:2016(ABNT NBR ISO 13485:2016) Medical Devices -- Quality management systems -- Requirements for regulatory purposes (巴西)

ID: SR 175

IEC 60601-1-6:2020/AMD2(ABNT NBR IEC 60601-1-6:2011) Medical electrical equipment - Part 1-6: General requirements for basic safety and essential performance - Collateral standard: Usability (巴西)

ID : SR 176

ISO 11137-1:2006/Amd 2:2018 Sterilization of health care products — Radiation — Part 1: Requirements for development, validation and routine control of a sterilization process for medical devices — Amendment 2: Revision to 4.3.4 and 11.2（巴西）

ID : SR 177

ISO 11137-2:2013/Amd 1:2022(ABNT NBR ISO 11137-2:2015) Sterilization of health care products — Radiation — Part 2: Establishing the sterilization dose — Amendment 1（巴西）

ID : SR 178

ISO 11607-1:2019(ABNT NBR ISO 11607-1:2013) Packaging for terminally sterilized medical devices — Part 1: Requirements for materials, sterile barrier systems and packaging systems (巴西)

ID : SR 179

ISO 11607-2:2019(ABNT NBR ISO 11607-2:2013) Packaging for terminally sterilized medical devices — Part 2: Validation requirements for forming, sealing and assembly processes (巴西)

ID: SR 180

ISO 11737-1:2018/Amd 1:2021 Sterilization of health care products — Microbiological methods — Part 1: Determination of a population of microorganisms on products — Amendment 1（巴西）

ID: SR 181

ISO 10993-2:2022(ABNT NBR ISO 10993-2:2021) Biological evaluation of medical devices — Part 2:

第21页共27页

========== 第 23 页 ==========

Animal welfare requirements（巴西）

ID : SR 182

ISO 10993-3:2014(ABNT NBR ISO 10993-3:2021) Biological evaluation of medical devices — Part 3: Tests for genotoxicity, carcinogenicity and reproductive toxicity (巴西)

ID: SR 183

ISO 10993-6:2016 Biological evaluation of medical devices — Part 6: Tests for local effects after implantation (巴西)

ID: SR 184

ISO 10993-11:2017(ABNT NBR ISO 10993-11:2023) Biological evaluation of medical devices — Part 11: Tests for systemic toxicity (巴西)

ID: SR 185

ISO 10993-12:2021(ABNT NBR ISO 10993-12:2016) Biological evaluation of medical devices - Part 12: Sample preparation and reference materials (巴西)

ID : SR 186

ISO 10993-18:2020/Amd 1:2022 Biological evaluation of medical devices — Part 18: Chemical characterization of medical device materials within a risk management process — Amendment 1: Determination of the uncertainty factor (巴西)

ID : SR 187

IEC 62366-1:2015/Amd 1:2020(ABNT NBR IEC 62366-1:2021 Emenda 1:2022/ABNT IEC/TR 62366-2:2021) Medical devices — Part 1: Application of usability engineering to medical devices (巴西)

ID : SR 188

ISO 7010:2019/Amd 6:2022 Graphical symbols — Safety colours and safety signs — Registered safety signs — Amendment 6（巴西）

ID: SR 189

ISO 780:2015 Packaging — Distribution packaging — Graphical symbols for handling and storage of packages（巴西）

ID: SR 190

ASTM F1886/F1886M:16 Standard Test Method for Determining Integrity of Seals for Flexible Packaging by Visual Inspection（巴西）

ID : SR 191

ASTM F1608:21 Standard Test Method for Microbial Ranking of Porous Packaging Materials (Exposure Chamber Method) (巴西)

ID : SR 192

ASTM F1140/F1140M:13(2020)e1 Standard Test Methods for Internal Pressurization Failure Resistance

第22页共27页

========== 第 24 页 ==========

of Unrestrained Packages（巴西）

ID: SR 193

ASTM D3078:02(2021)e1 Standard Test Method for Determination of Leaks in Flexible Packaging by Bubble Emission（巴西）

ID: SR 194

ASTM F1929:15 Standard Test Method for Detecting Seal Leaks in Porous Medical Packaging by Dye Penetration（巴西）

ID: SR 195

ISO/IEEE 11073-10425:2019 Health informatics — Personal health device communication — Part 10425: Device specialization — Continuous glucose monitor (CGM)（巴西）

ID: SR 196

ISO 15197:2013 In vitro diagnostic test systems — Requirements for blood-glucose monitoring systems for self-testing in managing diabetes mellitus (巴西)

ID: SR 197

ISO 14155:2020 Clinical investigation of medical devices for human subjects - Good clinical practice (巴西)

ID: SR 198

ISO/TR 20416:2020(ABNT ISO/TR 20416:2021) Medical devices — Post-market surveillance for manufacturers（巴西）

ID: SR 199

ISO/TR 24971:2020 Medical devices — Guidance on the application of ISO 14971（巴西）

ID: SR 200

IEC 82304-1:2016 Health software - Part 1: General requirements for product safety (巴西)

ID : SR 201

ISO 20417:2021(ABNT NBR ISO 20417:2022) Medical devices — Information to be supplied by the manufacturer（巴西）

ID : SR 202

IEC 60601-1-6 Edition 3.1 2013-10 Medical electrical equipment - Part 1-6: General requirements for basic safety and essential performance - Collateral standard: Usability（美国）

ID : SR 203

ISO 11137-1:2006/Amd 2:2018 Sterilization of health care products — Radiation — Part 1: Requirements for development, validation and routine control of a sterilization process for medical devices — Amendment 2: Revision to 4.3.4 and 11.2（美国）

第 23 页 共 27 页

========== 第 25 页 ==========

ID: SR 204

ISO 11137-2:2013/Amd 1:2022 Sterilization of health care products — Radiation — Part 2: Establishing the sterilization dose — Amendment 1（美国）

ID: SR 205

ISO 11607-1:2019-Ed.2.0 Packaging for terminally sterilized medical devices - Part 1: Requirements for materials, sterile barrier systems and packaging systems (美国)

ID : SR 206

ISO 11607-2:2019-Ed.2.0 Packaging for terminally sterilized medical devices - Part 2: Validation requirements for forming, sealing and assembly processes (美国)

ID : SR 207

ISO 11737-1:2018-Ed.3.0 Sterilization of medical devices - Microbiological methods - Part 1: Determination of population of microorganisms on products ISO 11737-1:2018-Ed.3.0/Amd.1:2021（美国）

ID : SR 208

ISO 10993-2 Third edition 2022-11 Biological Evaluation of medical devices - Part 2: Animal welfare requirements（美国）

ID : SR 209

ISO 10993-3 Third edition 2014-10-1 Biological evaluation of medical devices - Part 3: Tests for genotoxicity, carcinogenicity and reproductive toxicity (美国)

ID : SR 210

ISO 10993-6 Third edition 2016-12-01 Biological evaluation of medical devices -- Part 6: Tests for local effects after implantation (美国)

ID: SR 211

ISO 10993-11 Third edition 2017-09 Biological evaluation of medical devices - Part 11: Tests for systemic toxicity (美国)

ID : SR 212

ISO 10993-12 Fifth edition 2021-01 Biological evaluation of medical devices - Part 12: Sample preparation and reference materials（美国）

ID: SR 213

ISO 10993-18 Second edition 2020-01 Biological evaluation of medical devices - Part 18: Chemical characterization of medical device materials within a risk management process. (美国)

ID: SR 214

IEC 62366-1 Edition 1.1 2020-06 CONSOLIDATED VERSION Medical devices - Part 1: Application of usability engineering to medical devices (美国)

第24页共27页

========== 第 26 页 ==========

ID: SR 215

ISO 20417 First edition 2021-04 Corrected version 2021-12 Medical devices - Information to be supplied by the manufacturer（美国）

ID: SR 216

ISO 7010 Third edition 2019-07 Graphical symbols - Safety colours and safety signs - Registered safety signs（美国）

ID: SR 217

ASTM F1886/F1886M-16 Standard Test Method for Determining Integrity of Seals for Flexible Packaging by Visual Inspection（美国）

ID: SR 218

ASTM F1608-21 Standard Test Method for Microbial Ranking of Porous Packaging Materials (Exposure Chamber Method)（美国）

ID: SR 219

ASTMF1140/F1140M-13 (Reapproved 2020)e1 Standard Test Methods for Internal Pressurization Failure Resistance of Unrestrained Packages（美国）

ID: SR 220

ASTM D3078-02 (Reapproved 2021)e1 Standard Test Method for Determination of Leaks in Flexible Packaging by Bubble Emission (美国)

ID: SR 221

ASTM F1929-15 Standard Test Method for Detecting Seal Leaks in Porous Medical Packaging by Dye Penetration（美国）

ID: SR 222

ISO 14155:2020-Ed.3.0 Clinical investigation of medical devices for human subjects - Good clinical practice（美国）

ID: SR 223

CLSI POCT05 2nd Edition Performance Metrics for Continuous Interstitial Glucose Monitoring（美国）

ID : SR 224

IEEE ISO 11073-10425 First edition 2016-06-15 Health informatics - Personal health device communication - Part 10425: Device specialization - Continuous glucose monitor (CGM) (美国)

ID: SR 225

ISO/TR 24971:2020 Medical devices — Guidance on the application of ISO 14971（美国）

ID : SR 226

IEC 82304-1 Edition 1.0 Health software - Part 1: General requirements for product safety（美国）

第25页共27页

========== 第 27 页 ==========

ID : SR 227

No. 21, 1990 Therapeutic Goods Act 1989（澳大利亚）

ID: SR 228

Statutory Rules No. 394, 1990 Therapeutic Goods Regulations 1990（澳大利亚）

ID: SR 229

Statutory Rules No. 236, 2002 Therapeutic Goods (Medical Devices) Regulations 2002（澳大利亚）

ID: SR 230

ISO 13485:2016(AS ISO 13485:2017) Medical devices - Quality management systems - Requirements for regulatory purposes（澳大利亚）

ID: SR 231

IEC 60601-1-6:2010/AMD2:2020 Medical electrical equipment - Part 1-6: General requirements for basic safety and essential performance - Collateral standard: Usability（澳大利亚）

ID: SR 232

ISO 11137-1:2006/Amd 2:2018 Sterilization of health care products — Radiation — Part 1: Requirements for development, validation and routine control of a sterilization process for medical devices (澳大利亚)

ID: SR 233

ISO 11137-2:2013/Amd 1:2022 Sterilization of health care products — Radiation — Part 2: Establishing the sterilization dose（澳大利亚）

ID : SR 234

ISO 11737-1:2018/Amd 1:2021 Sterilization of health care products — Microbiological methods — Part 1: Determination of a population of microorganisms on products（澳大利亚）

ID: SR 235

ISO 11737-2:2019 Sterilization of health care products — Microbiological methods — Part 2: Tests of sterility performed in the definition, validation and maintenance of a sterilization process（澳大利亚）

ID: SR 236

ISO 11607-1:2019 Packaging for terminally sterilized medical devices — Part 1: Requirements for materials, sterile barrier systems and packaging systems（澳大利亚）

ID : SR 237

ISO 11607-2:2019 Packaging for terminally sterilized medical devices — Part 2: Validation requirements for forming, sealing and assembly processes (澳大利亚)

ID: SR 238

ISO 10993-2:2022 Biological evaluation of medical devices — Part 2: Animal welfare requirements（澳大利亚）

第26页共27页

========== 第 28 页 ==========

ID: SR 239

ISO 10993-3:2014 Biological evaluation of medical devices — Part 3: Tests for genotoxicity, carcinogenicity and reproductive toxicity（澳大利亚）

ID: SR 240

ISO 10993-6:2016 Biological evaluation of medical devices — Part 6: Tests for local effects after implantation (澳大利亚)

ID: SR 241

ISO 10993-11:2017 Biological evaluation of medical devices — Part 11: Tests for systemic toxicity (澳大利亚)

ID: SR 242

ISO 10993-12:2021 Biological evaluation of medical devices — Part 12: Sample preparation and reference materials（澳大利亚）

ID: SR 243

ISO 10993-18:2020 Biological evaluation of medical devices — Part 18: Chemical characterization of medical device materials within a risk management process（澳大利亚）

ID: SR 244

IEC 62366-1:2015/Amd 1:2020 Medical devices - Part 1: Application of usability engineering to medical devices（澳大利亚）

ID: SR 245

ISO 20417:2021 Medical devices - Information to be provided by the manufacturer（澳大利亚）

ID: SR 246

ISO 780:2015 Packaging — Distribution packaging — Graphical symbols for handling and storage of packages（澳大利亚）

ID: SR 247

ISO 7010:2019/Amd 6:2022 Graphical symbols — Safety colours and safety signs — Registered safety signs（澳大利亚）

ID: SR 248

ISO/TR 24971:2020(SA TR ISO 24971:2020) Medical devices — Guidance on the application of ISO 14971（澳大利亚）

ID: SR 249

IEC 82304-1:2016(AS IEC 82304.1:2022) Health software - Part 1: General requirements for product safety（澳大利亚）

第27页共27页