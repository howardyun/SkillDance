## Category Matrix
大类	小类	安全定义	数据等级	主要风险	控制要求
数据访问类	会话与上下文访问	允许读取当前会话、历史上下文、会话附件和输入信息；风险核心在于上下文中可能混入敏感信息、凭证、个人信息或跨任务信息拼接	P1-P3	I、E、T	最小化读取；敏感内容脱敏；禁止无关历史拼接；外发前确认；访问留痕
数据访问类	文件与知识库访问	允许读取文件库、知识库、内部文档和授权资料；风险核心在于越权读取、批量抽取、内部资料外泄	P1-P3	I、E、R	权限继承；来源白名单；按文档/库粒度授权；禁止批量导出；引用与审计日志
数据访问类	外部信息访问	允许访问互联网公开网页、公开API、在线资料；风险核心在于不可信内容注入、恶意链接、污染决策依据	P0-P1（输入面不可信）	T、I、D、E	外部内容视为不可信；域名/API白名单；禁止将网页内容直接转为高权限动作；保留来源引用
能力执行类	检索与查询执行	允许调用只读型工具做搜索、筛选、查询；风险核心在于读取邮件、日历、记录时产生敏感信息暴露或过度检索	P1-P3	I、R、E	工具只读；查询范围限制；结果最小化返回；敏感字段遮蔽；审计查询行为
能力执行类	代码与计算执行	允许运行代码、脚本、容器任务或数据处理逻辑；风险核心在于执行环境越权、数据泄露、资源滥用、生成错误结果并被继续使用	P1-P3	T、D、E、I	沙箱隔离；网络/文件系统限制；依赖白名单；资源配额；输出检查；高敏任务禁外连
能力执行类	内容生成与文件处理	允许生成新内容或加工文件，但不直接写回外部系统；风险核心在于将敏感数据写入输出物、误生成、错误引用	P1-P3	I、T、R	输出脱敏；来源标注；人工复核；禁止自动分发；文件元数据与访问范围控制
业务操作类	草稿与建议写入	允许生成草稿、建议修改、预填内容，但不直接提交；风险核心在于草稿内容错误、误收件人、带出敏感信息	P1-P3	T、I、R	仅生成草稿；变更预览；收件人/目标对象确认；敏感词扫描；保留审批痕迹
业务操作类	受确认的单次写入	允许在用户明确确认后执行一次写入或修改；风险核心在于误操作、错误对象、不可逆修改	P1-P3	T、R、E、I	显式确认；目标对象回显；操作前预览；幂等控制；可回滚优先；完整操作日志
业务操作类	自动或批量写入	允许自动执行写入，或一次性批量修改多条数据；风险核心在于规模化错误、越权扩散、批量破坏	P1-P3	T、R、E、D、I	批量上限；先dry-run；双重审批；回滚机制；异常中止；变更审计；最小权限
代理自动化类	跨应用身份代理	允许以用户授权身份跨多个系统联动；风险核心在于跨系统权限扩大、数据拼接泄露、责任边界不清	P1-P3	E、I、T、R	分系统授权；连接器白名单；禁止隐式权限继承；跨系统数据流约束；全链路审计
代理自动化类	定时与周期自动化	允许按固定时间周期执行任务；风险核心在于长期无人值守、授权过期、任务漂移、错误持续重复	P1-P3	R、T、I、D	任务owner；定期复审；可暂停/kill switch；运行日志；权限过期校验；默认只读优先
代理自动化类	条件触发与监控自动化	允许持续监控条件并自动触发动作；风险核心在于误触发、过度监控、通知风暴、自动执行破坏性动作	P1-P3	D、I、R、E、T	触发阈值治理；频率限制；误报保护；默认通知优先、动作后置；高风险动作必须人工确认

## Atomic Capabilities
原子ID	原子能力	最小成立条件	主要风险	必要控制
R1	读取当前用户输入	明确消费当前 prompt 或 input 参数	I、T	最小化读取；脱敏
R2	读取当前会话历史	存在 chat history 或 previous turns 读取接口	I、E、T	最小化读取；访问留痕
R3	读取历史会话	存在跨会话检索或历史存储访问	I、E、T	按需授权；时间窗限制
R4	读取会话附件	存在 attachment 或 file input 读取	I、T	附件范围限制；敏感扫描
R5	读取本地 repo 文件	明确 read/cat/open/glob/grep 项目文件	I、E	路径范围限制
R6	读取本地任意路径文件	可访问 repo 外路径或绝对路径	I、E、R	目录白名单
R7	读取知识库或文档库	存在 KB、Drive、Docs、内部文档读取接口	I、E、R	文档级授权；审计
R8	读取连接器数据	存在 Gmail、Slack、Notion、GitHub 等 connector 读接口	I、E、R	分系统授权
R9	批量枚举文件或资源	存在 list/search all 或 bulk export 行为	I、E、R、D	分页；条数上限
R10	跨源数据拼接读取	将会话、附件、文件、连接器、网页数据合并分析	I、E、T	跨源拼接告警
W1	访问公开网页	存在真实网络读取，如 browser、http get、web fetch	T、I、D、E	域名白名单；来源标注
W2	调用外部公开 API	存在明确 REST 或 SDK API 调用	T、I、D、E	API 白名单；字段限制
W3	下载外部文件	存在 download 或 fetch file 行为	T、I、D	类型限制；恶意扫描
W4	使用外部搜索结果驱动后续动作	网页结果直接进入计划或动作链	T、I、E	人工复核
Q1	只读查询或搜索	search、query、filter、list 等只读工具	I、R、E	只读约束；范围限制
Q2	结构化筛选与聚合	select、group、aggregate 且不写回	I、R	最小化结果
Q3	敏感对象查询	查询邮件、日历、联系人、工单等	I、R、E	字段遮蔽；按对象授权
Q4	自动推荐或判定	基于检索结果给出建议、分类、优先级	T、R	来源标注；人工复核
X1	执行 shell 命令	存在 exec、spawn、bash、sh 等真实执行 sink	T、D、E、I	沙箱；命令白名单
X2	执行解释器代码	存在 python、node、ruby 等运行时执行	T、D、E、I	沙箱；依赖限制
X3	执行容器任务	存在 docker、container、job runner	T、D、E、I	镜像白名单；网络限制
X4	安装依赖或拉取包	存在 pip、npm、apt、cargo install	T、D、E	源白名单；锁版本
X5	执行环境可联网	执行环境同时具备网络访问	T、E、I、D	高敏任务禁网
X6	执行环境可写文件系统	执行环境可修改本地文件	T、I、D	路径白名单；写前预览
X7	访问环境变量或凭证	读取 env、secret、token、credential store	E、I	secret manager；禁止明文输出
X8	调用外部二进制或本地工具	调用 git、docker、curl 或自定义 CLI	T、D、E	工具白名单
G1	生成文本建议	输出分析、建议、草稿，但不写回系统	T、I、R	来源标注；敏感扫描
G2	生成结构化草稿	预填表单、邮件草稿、PR 描述等	T、I、R	仅草稿；目标确认
G3	写本地临时文件	写 temp、report、cache、output	I、T、R	输出脱敏；元数据控制
G4	写本地项目文件	修改 repo 或工作区文件	T、R、I	diff 预览；路径限制
G5	批量本地写文件	多文件修改或生成	T、R、D、I	文件数上限；dry-run
O1	创建外部草稿	create_draft 或 save_draft	T、I、R	仅草稿；目标确认
O2	外部单对象写入	create 或 update one object after trigger	T、R、E、I	显式确认；预览
O3	外部多对象批量写入	loop 或 batch apply many objects	T、R、E、D、I	条数上限；dry-run
O4	破坏性写入	delete、archive、reset、revoke	T、R、D、E	双确认；回滚
O5	自动外发	send email、publish、post without second confirmation	I、T、R、E	发送前确认
A1	用户显式单次触发	仅在当前指令下执行	T、R	默认模式
A2	需确认后执行	流程中明确 wait for confirmation 或 approve	T、R	显式确认
A3	定时调度	存在 cron、scheduler、fixed interval job registration	R、T、I、D	owner；kill switch
A4	事件触发	hook、webhook、on event、on message	D、I、R、E、T	误触发保护
A5	持续监控	daemon、watch、poll、long-running loop	D、I、R	频率限制；暂停开关
A6	触发后自动动作	监控满足条件后直接执行写入或外发	D、I、R、E、T	人工确认优先
A7	自动重试或循环执行	retry loop、backoff、repeated attempts	D、R、T	次数上限；异常中止
I1	使用当前用户身份访问单系统	connector 以用户授权身份读写	E、I、R	分系统授权
I2	跨系统身份代理	同一任务中以用户身份操作多个系统	E、I、T、R	连接器白名单
I3	跨系统数据搬运	从 A 系统读数据写入 B 系统	E、I、T、R	字段白名单；数据流约束
I4	凭证注入到外部调用	token 或 api key 被传入命令或 API	E、I	禁止明文传递
I5	隐式权限继承	未单独声明却沿用高权限 connector	E、R、I	显式授权；权限分离

## Control Semantics
控制ID	控制语义	最小成立条件	适用原子能力
C1	只读约束	明确声明只读，或实现存在读取而无写入 sink	R1,R2,R3,R4,R5,R6,R7,R8,R9,R10,W1,W2,W3,W4,Q1,Q2,Q3,Q4
C2	范围限制	有 path、domain、query 或 object scope	R5,R6,R7,R8,R9,R10,Q1,Q2,Q3
C3	显式确认	代码或流程里明确等待用户确认	G4,O2,O3,O4,O5,A2,A6
C4	预览或回显	写前展示对象、diff、收件人、参数	G4,O2,O3,O4
C5	dry-run	存在不落地预执行模式	G5,O3,A6
C6	回滚或幂等	可撤销或重复执行不扩大影响	G4,G5,O2,O3,O4
C7	白名单	域名、API、工具或连接器白名单	W1,W2,W3,X4,X8,I2,I3,I4
C8	脱敏	敏感字段检测与遮蔽	R1,R2,R3,R4,R5,R6,R7,R8,R9,R10,G1,G2,G3
C9	审计日志	对查询、写入、自动化保留日志	R8,R9,Q1,Q2,Q3,Q4,O2,O3,O4,A3,A4,A5,A6
C10	kill switch	可暂停或停用自动任务	A3,A4,A5,A6
C11	频率或规模限制	具备 rate limit、batch cap 或 retry cap	O3,A4,A5,A6,A7
C12	高敏禁外连	高敏执行默认禁网	X1,X2,X3,X4,X5,X6,X7,X8

## Capability Mappings
原子ID	上卷类目
R1	session_context_access
R2	session_context_access
R3	session_context_access
R4	session_context_access
R10	session_context_access
R5	file_knowledge_access
R6	file_knowledge_access
R7	file_knowledge_access
R8	file_knowledge_access
R9	file_knowledge_access
R10	file_knowledge_access
W1	external_information_access
W2	external_information_access
W3	external_information_access
W4	external_information_access
Q1	retrieval_query_execution
Q2	retrieval_query_execution
Q3	retrieval_query_execution
Q4	retrieval_query_execution
R7	retrieval_query_execution
R8	retrieval_query_execution
R9	retrieval_query_execution
X1	code_computation_execution
X2	code_computation_execution
X3	code_computation_execution
X4	code_computation_execution
X5	code_computation_execution
X6	code_computation_execution
X7	code_computation_execution
X8	code_computation_execution
G1	content_generation_file_processing
G2	content_generation_file_processing
G3	content_generation_file_processing
G4	content_generation_file_processing
G5	content_generation_file_processing
G1	draft_suggestion_write
G2	draft_suggestion_write
O1	draft_suggestion_write
G4	confirmed_single_write
O2	confirmed_single_write
O4	confirmed_single_write
A2	confirmed_single_write
G5	automatic_batch_write
O3	automatic_batch_write
O4	automatic_batch_write
O5	automatic_batch_write
A6	automatic_batch_write
I1	cross_app_identity_proxy
I2	cross_app_identity_proxy
I3	cross_app_identity_proxy
I4	cross_app_identity_proxy
I5	cross_app_identity_proxy
R10	cross_app_identity_proxy
A3	scheduled_periodic_automation
A7	scheduled_periodic_automation
A4	conditional_trigger_monitoring_automation
A5	conditional_trigger_monitoring_automation
A6	conditional_trigger_monitoring_automation

## Mismatch Definitions
MismatchID	名称	定义	触发条件
M1	declaration_missing	缺少声明层能力图谱	无声明层能力，但实现层存在成立能力
M2	capability_underreported	实现能力大于声明能力	impl=true, claim=false
M3	capability_overreported	声明能力大于实现能力	claim=true, impl=false
M4	control_missing	声明控制存在但实现未体现	claim(control)=true, impl(control)=false
M5	scope_drift	声明为单对象或单系统，实际扩展到批量或跨系统	scope mismatch
M6	autonomy_drift	声明为手动或草稿，实际存在自动执行	autonomy mismatch
M7	insufficient_evidence	只有弱证据，没有满足最小成立条件	weak evidence only
