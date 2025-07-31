document.addEventListener('DOMContentLoaded', () => {
    // ########################
    // ### 글로벌 상태 및 상수 ###
    // ########################
    const state = {
        process_mode: '이적실',
        start_date: '',
        end_date: '',
        selected_workers: [],
        active_tab: '',
        full_data: null,
        charts: {}, // 생성된 차트 인스턴스 저장
        worker_detail: { // 작업자별 분석 탭 상태
            sort_key: '종합 점수 높은 순',
            selected_worker: null,
        },
        comparison_period: '일간', // 공정 비교 탭 기간
    };

    const TAB_CONFIG = {
        "이적실": ["실시간 현황", "생산량 분석", "작업자별 분석", "오류 로그", "생산 이력 추적", "상세 데이터"],
        "검사실": ["실시간 현황", "검사량 분석", "작업자별 분석", "오류 로그", "생산 이력 추적", "상세 데이터"],
        "포장실": ["실시간 현황", "생산량 추이 분석", "오류 로그", "생산 이력 추적", "상세 데이터"],
        "전체 비교": ["공정 비교 분석", "생산 이력 추적", "상세 데이터"],
    };
    
    const RADAR_METRICS_CONFIG = {
        "포장실": { '세트완료시간': 'avg_work_time', '첫스캔준비성': 'avg_latency', '무결점달성률': 'first_pass_yield', '세트당PCS': 'avg_pcs_per_tray' },
        "이적실": { '신속성': 'avg_work_time', '준비성': 'avg_latency', '초도수율': 'first_pass_yield', '안정성': 'work_time_std' },
        "검사실": { '신속성': 'avg_work_time', '준비성': 'avg_latency', '무결점달성률': 'first_pass_yield', '안정성': 'work_time_std', '품질 정확도': 'defect_rate' }
    };
    RADAR_METRICS_CONFIG['전체 비교'] = RADAR_METRICS_CONFIG['이적실'];


    // ########################
    // ### DOM 요소 캐싱 ###
    // ########################
    const elements = {
        loadingOverlay: document.getElementById('loading-overlay'),
        processModeRadios: document.getElementById('process-mode-radios'),
        startDateInput: document.getElementById('start-date-input'),
        endDateInput: document.getElementById('end-date-input'),
        workerList: document.getElementById('worker-list'),
        runAnalysisBtn: document.getElementById('run-analysis-btn'),
        resetFiltersBtn: document.getElementById('reset-filters-btn'),
        mainTitle: document.getElementById('main-title'),
        tabsContainer: document.querySelector('.tabs'),
        tabContentContainer: document.querySelector('.tab-content'),
    };

    // ########################
    // ### 초기화 ###
    // ########################
    const socket = io();
    socket.on('connect', () => console.log('Socket.IO 서버에 연결되었습니다.'));
    socket.on('disconnect', () => console.log('Socket.IO 서버 연결이 끊어졌습니다.'));
    socket.on('data_updated', (data) => {
        console.log('서버로부터 데이터 업데이트 이벤트를 받았습니다:', data.message);
        if (state.active_tab === '실시간 현황') {
            showToast('실시간 데이터가 업데이트되었습니다. 갱신합니다...');
            renderActiveTabData();
        } else {
            showToast('새로운 데이터가 감지되었습니다. 실시간 현황 탭에서 확인할 수 있습니다.');
        }
    });

    initialize();

    function initialize() {
        bindEventListeners();
        fetchAnalysisData();
    }

    // ########################
    // ### 이벤트 리스너 ###
    // ########################
    function bindEventListeners() {
        elements.processModeRadios.addEventListener('change', handleProcessModeChange);
        elements.runAnalysisBtn.addEventListener('click', () => fetchAnalysisData());
        elements.resetFiltersBtn.addEventListener('click', resetFiltersAndRunAnalysis);
    }

    // ########################
    // ### 이벤트 핸들러 ###
    // ########################
    function handleProcessModeChange(event) {
        if (event.target.name === 'process_mode') {
            state.process_mode = event.target.value;
            elements.mainTitle.textContent = `${state.process_mode} 대시보드`;

            if (state.process_mode === '전체 비교') {
                const today = new Date().toISOString().split('T')[0];
                elements.startDateInput.value = today;
                elements.endDateInput.value = today;
            }

            fetchAnalysisData();
        }
    }

    function resetFiltersAndRunAnalysis() {
        if (state.full_data && state.full_data.date_range) {
            elements.startDateInput.value = state.full_data.date_range.min;
            elements.endDateInput.value = state.full_data.date_range.max;
        }
        for (let option of elements.workerList.options) {
            option.selected = true;
        }
        fetchAnalysisData();
    }

    function handleTabClick(event) {
        if (event.target.classList.contains('tab-btn')) {
            const newTab = event.target.dataset.tab;
            if (newTab !== state.active_tab) {
                state.active_tab = newTab;
                updateActiveTabUI();
                renderActiveTabData();
            }
        }
    }

    // ########################
    // ### API 통신 ###
    // ########################
    async function fetchAnalysisData() {
        toggleLoading(true);
        state.start_date = elements.startDateInput.value;
        state.end_date = elements.endDateInput.value;
        state.selected_workers = Array.from(elements.workerList.selectedOptions).map(opt => opt.value);

        try {
            const response = await fetch('/api/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    process_mode: state.process_mode,
                    start_date: state.start_date,
                    end_date: state.end_date,
                    selected_workers: state.selected_workers,
                }),
            });
            if (!response.ok) throw new Error((await response.json()).error || `HTTP Error: ${response.status}`);
            const data = await response.json();
            state.full_data = data;
            updateDashboard(data);
        } catch (error) {
            console.error('데이터 분석 중 오류 발생:', error);
            alert(`데이터를 불러오는 데 실패했습니다: ${error.message}`);
        } finally {
            toggleLoading(false);
        }
    }

    async function fetchRealtimeData() {
        try {
            const response = await fetch(`/api/realtime?process_mode=${state.process_mode}`);
            if (!response.ok) throw new Error('실시간 데이터 로드 실패');
            return await response.json();
        } catch (error) {
            console.error('실시간 데이터 API 호출 오류:', error);
            return null;
        }
    }

    // ########################
    // ### 메인 UI 렌더링 ###
    // ########################
    function toggleLoading(isLoading) {
        elements.loadingOverlay.classList.toggle('hidden', !isLoading);
        elements.runAnalysisBtn.disabled = isLoading;
    }

    function updateDashboard(data) {
        renderFilterControls(data.workers, data.date_range);
        renderTabs();
        renderActiveTabData();
    }

    function renderFilterControls(workers, date_range) {
        const currentSelection = new Set(Array.from(elements.workerList.selectedOptions).map(opt => opt.value));
        elements.workerList.innerHTML = '';
        workers.forEach(worker => {
            const option = document.createElement('option');
            option.value = worker;
            option.textContent = worker;
            if (currentSelection.size === 0 || currentSelection.has(worker)) {
                option.selected = true;
            }
            elements.workerList.appendChild(option);
        });

        if (!elements.startDateInput.value && date_range.min) elements.startDateInput.value = date_range.min;
        if (!elements.endDateInput.value && date_range.max) elements.endDateInput.value = date_range.max;
    }

    function renderTabs() {
        elements.tabsContainer.innerHTML = '';
        const tabsForMode = TAB_CONFIG[state.process_mode];
        tabsForMode.forEach(tabName => {
            const tabButton = document.createElement('button');
            tabButton.className = 'tab-btn';
            tabButton.textContent = tabName;
            tabButton.dataset.tab = tabName;
            elements.tabsContainer.appendChild(tabButton);
        });

        if (tabsForMode.length > 0 && !tabsForMode.includes(state.active_tab)) {
            state.active_tab = tabsForMode[0];
        }
        updateActiveTabUI();
        elements.tabsContainer.removeEventListener('click', handleTabClick);
        elements.tabsContainer.addEventListener('click', handleTabClick);
    }

    function updateActiveTabUI() {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === state.active_tab);
        });
    }

    function renderActiveTabData() {
        Object.values(state.charts).forEach(chart => chart.destroy());
        state.charts = {};
        elements.tabContentContainer.innerHTML = '';
        if (!state.full_data) return;

        const pane = document.createElement('div');
        pane.className = 'tab-pane active';
        elements.tabContentContainer.appendChild(pane);

        const renderFunction = getRenderFunctionForTab(state.active_tab);
        renderFunction(pane, state.full_data);
    }
    
    function getRenderFunctionForTab(tabName) {
        const mapping = {
            '실시간 현황': renderRealtimeTab,
            '생산량 분석': renderProductionTab,
            '검사량 분석': renderProductionTab,
            '생산량 추이 분석': renderProductionTab,
            '작업자별 분석': renderWorkerDetailTab,
            '오류 로그': renderErrorLogTab,
            '생산 이력 추적': renderTraceabilityTab,
            '상세 데이터': renderFullDataTableTab,
            '공정 비교 분석': renderComparisonTab,
        };
        return mapping[tabName] || ((pane) => pane.innerHTML = `<p>${tabName} 탭을 찾을 수 없습니다.</p>`);
    }

    // ########################
    // ### 탭별 렌더링 함수 ###
    // ########################

    async function renderRealtimeTab(pane) {
        pane.innerHTML = `
            <div class="kpi-grid">
                <div id="realtime-worker-status" class="card"></div>
                <div id="realtime-item-status" class="card"></div>
            </div>
            <div class="card">
                <div class="chart-container" id="realtime-hourly-chart-container">
                    <canvas id="realtime-hourly-chart"></canvas>
                </div>
            </div>`;
        
        const realtimeData = await fetchRealtimeData();
        if (!realtimeData) {
            pane.innerHTML = '<p>실시간 데이터를 불러오는 데 실패했습니다.</p>';
            return;
        }

        const workerStatusEl = pane.querySelector('#realtime-worker-status');
        workerStatusEl.innerHTML = '<h3>작업자별 실시간 현황 (오늘)</h3>';
        if(realtimeData.worker_status.length > 0) {
            const workerTable = createTable(
                ['작업자', '총 PCS', '평균 시간(초)', '세트 수'],
                realtimeData.worker_status.map(w => [w.worker, w.pcs_completed, w.avg_work_time.toFixed(1), w.session_count])
            );
            workerStatusEl.appendChild(workerTable);
        } else {
            workerStatusEl.innerHTML += '<p>데이터 없음</p>';
        }

        const itemStatusEl = pane.querySelector('#realtime-item-status');
        itemStatusEl.innerHTML = '<h3>품목별 실시간 현황 (오늘)</h3>';
        if(realtimeData.item_status.length > 0) {
            const itemTable = createTable(
                ['품목', '생산량 (PCS)'],
                realtimeData.item_status.map(i => [i.item_display, i.pcs_completed])
            );
            itemStatusEl.appendChild(itemTable);
        } else {
            itemStatusEl.innerHTML += '<p>데이터 없음</p>';
        }

        createChart('realtime-hourly-chart', 'bar', {
            labels: realtimeData.hourly_production.labels,
            datasets: [{
                label: '오늘 생산량',
                data: realtimeData.hourly_production.data,
                backgroundColor: 'rgba(0, 82, 204, 0.6)',
            }]
        }, { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, title: { text: '완료 PCS 수', display: true } } } });
    }

    function renderProductionTab(pane, data) {
        pane.innerHTML = `
            <div class="kpi-grid">
                ${createCard('평균 트레이 작업시간', formatSeconds(data.kpis.avg_tray_time || 0))}
                ${createCard('평균 작업 준비시간', formatSeconds(data.kpis.avg_latency || 0))}
                ${createCard('초도 수율 (FPY)', `${(data.kpis.avg_fpy * 100).toFixed(1)}%`, 'positive')}
            </div>
            <div class="card">
                 <div class="chart-container"><canvas id="production-trend-chart"></canvas></div>
            </div>`;
        
        const sessions = data.filtered_sessions_data;
        const productionByDate = sessions.reduce((acc, session) => {
            const date = session.date.split('T')[0];
            acc[date] = (acc[date] || 0) + session.pcs_completed;
            return acc;
        }, {});
        
        const sortedDates = Object.keys(productionByDate).sort();
        createChart('production-trend-chart', 'line', {
            labels: sortedDates,
            datasets: [{
                label: '일별 총 생산량 (PCS)',
                data: sortedDates.map(date => productionByDate[date]),
                borderColor: 'var(--color-primary)',
                backgroundColor: 'rgba(0, 82, 204, 0.1)',
                fill: true,
                tension: 0.1
            }]
        }, { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } });
    }

    function renderWorkerDetailTab(pane, data) {
        if (!data.worker_data || data.worker_data.length === 0) {
            pane.innerHTML = '<p>분석할 작업자 데이터가 없습니다.</p>';
            return;
        }

        pane.innerHTML = `
            <div class="worker-detail-layout">
                <div class="worker-list-pane card">
                    <div class="filter-group">
                        <label for="worker-sort-select">정렬 기준</label>
                        <select id="worker-sort-select">
                            <option>종합 점수 높은 순</option>
                            <option>종합 점수 낮은 순</option>
                            <option>이름순</option>
                            <option>평균 작업 시간 빠른 순</option>
                            <option>평균 작업 시간 느린 순</option>
                            <option>처리 세트 많은 순</option>
                        </select>
                    </div>
                    <ul id="detail-worker-list"></ul>
                </div>
                <div class="worker-detail-pane" id="worker-detail-content">
                    <p>왼쪽 목록에서 작업자를 선택해주세요.</p>
                </div>
            </div>`;

        const sortSelect = pane.querySelector('#worker-sort-select');
        sortSelect.value = state.worker_detail.sort_key;
        sortSelect.addEventListener('change', (e) => {
            state.worker_detail.sort_key = e.target.value;
            renderSortedWorkerList(data);
        });

        renderSortedWorkerList(data);
    }
    
    function renderSortedWorkerList(data) {
        const listEl = document.getElementById('detail-worker-list');
        if (!listEl) return;

        const sortedWorkers = sortWorkers(data.worker_data, state.worker_detail.sort_key);
        
        listEl.innerHTML = '';
        sortedWorkers.forEach(worker => {
            const li = document.createElement('li');
            li.textContent = worker.worker;
            li.dataset.workerName = worker.worker;
            if (state.worker_detail.selected_worker === worker.worker) {
                li.classList.add('active');
            }
            listEl.appendChild(li);
        });

        listEl.removeEventListener('click', handleWorkerSelection);
        listEl.addEventListener('click', handleWorkerSelection);

        if (sortedWorkers.length > 0 && (!state.worker_detail.selected_worker || !sortedWorkers.find(w => w.worker === state.worker_detail.selected_worker))) {
            state.worker_detail.selected_worker = sortedWorkers[0].worker;
        }
        
        if (state.worker_detail.selected_worker) {
            const activeLi = listEl.querySelector(`[data-worker-name="${state.worker_detail.selected_worker}"]`);
            if (activeLi) activeLi.classList.add('active');
            renderWorkerDetails(state.worker_detail.selected_worker, data);
        }
    }

    function handleWorkerSelection(e) {
        if (e.target.tagName === 'LI') {
            const workerName = e.target.dataset.workerName;
            state.worker_detail.selected_worker = workerName;
            
            const listEl = document.getElementById('detail-worker-list');
            listEl.querySelectorAll('li').forEach(li => li.classList.remove('active'));
            e.target.classList.add('active');

            renderWorkerDetails(workerName, state.full_data);
        }
    }

    function renderWorkerDetails(workerName, data) {
        const contentPane = document.getElementById('worker-detail-content');
        const workerPerf = data.worker_data.find(w => w.worker === workerName);
        const workerNorm = data.normalized_performance.find(w => w.worker === workerName);

        if (!workerPerf || !workerNorm) {
            contentPane.innerHTML = '<p>선택된 작업자의 상세 데이터를 찾을 수 없습니다.</p>';
            return;
        }
        
        const bestTimeText = workerPerf.best_work_time_date 
            ? `(금주 최고: ${formatSeconds(workerPerf.best_work_time)} / ${new Date(workerPerf.best_work_time_date).toLocaleDateString()})`
            : '';

        contentPane.innerHTML = `
            <div class="kpi-grid kpi-grid-4-cols">
                ${createCard('종합 성과 점수', `${workerPerf.overall_score.toFixed(1)} 점`)}
                ${createCard('평균 작업 시간', formatSeconds(workerPerf.avg_work_time), '', bestTimeText)}
                ${createCard('평균 준비 시간', formatSeconds(workerPerf.avg_latency))}
                ${createCard('초도 수율', `${(workerPerf.first_pass_yield * 100).toFixed(1)}%`)}
            </div>
            <div class="worker-charts-layout">
                <div class="card">
                    <h4>성과 레이더 차트</h4>
                    <div class="chart-container" style="height: 300px;"><canvas id="worker-radar-chart"></canvas></div>
                </div>
                <div class="card">
                    <h4>품목별 성과</h4>
                    <div id="item-perf-table-container" class="table-container"></div>
                </div>
            </div>`;

        const radarMetrics = RADAR_METRICS_CONFIG[state.process_mode];
        const labels = Object.keys(radarMetrics);
        const chartData = labels.map(label => {
            const metricKey = radarMetrics[label];
            return (workerNorm[`${metricKey}_norm`] || 0) * 100;
        });

        createChart('worker-radar-chart', 'radar', {
            labels: labels,
            datasets: [{
                label: workerName,
                data: chartData,
                backgroundColor: 'rgba(0, 82, 204, 0.2)',
                borderColor: 'rgb(0, 82, 204)',
            }]
        }, { responsive: true, maintainAspectRatio: false, scales: { r: { beginAtZero: true, max: 100, min: 0 } } });

        const workerSessions = data.filtered_sessions_data.filter(s => s.worker === workerName);
        const itemPerf = workerSessions.reduce((acc, s) => {
            const key = `${s.item_display} / ${s.phase || 'N/A'}차`;
            if (!acc[key]) acc[key] = { times: [], count: 0 };
            acc[key].times.push(s.work_time);
            acc[key].count++;
            return acc;
        }, {});

        const tableRows = Object.entries(itemPerf).map(([itemName, stats]) => {
            const avgTime = stats.times.reduce((a, b) => a + b, 0) / stats.times.length;
            return [itemName, formatSeconds(avgTime), stats.count];
        });

        const tableContainer = contentPane.querySelector('#item-perf-table-container');
        const table = createTable(['품목/차수', '평균시간', '처리 세트 수'], tableRows);
        tableContainer.appendChild(table);
    }

    function renderErrorLogTab(pane, data) {
        const errorEvents = (data.filtered_raw_events || []).filter(event => 
            event.event && (event.event.toLowerCase().includes('error') ||
            event.event.toLowerCase().includes('fail') ||
            event.event.toLowerCase().includes('cancel'))
        ).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

        pane.innerHTML = `
            <div class="tab-header">
                <h3>오류 로그</h3>
                <button id="export-error-csv" class="btn">CSV로 내보내기</button>
            </div>`;

        if (errorEvents.length === 0) {
            pane.innerHTML += '<p>선택된 기간/작업자에 해당하는 오류 기록이 없습니다.</p>';
            pane.querySelector('#export-error-csv').disabled = true;
            return;
        }

        const table = createTable(
            ['시간', '작업자', '오류 유형', '상세 정보'],
            errorEvents.map(e => [
                new Date(e.timestamp).toLocaleString(),
                e.worker,
                e.event,
                typeof e.details === 'object' ? JSON.stringify(e.details) : e.details
            ])
        );
        const container = document.createElement('div');
        container.className = 'table-container';
        container.appendChild(table);
        pane.appendChild(container);

        pane.querySelector('#export-error-csv').addEventListener('click', () => {
            exportToCSV(errorEvents, `error_log_${new Date().toISOString().split('T')[0]}.csv`);
        });
    }

    function renderTraceabilityTab(pane, data) {
        pane.innerHTML = `
            <div class="card">
                <div class="trace-search-form">
                    <div class="form-group">
                        <label for="trace-wid">작업지시 ID (WID):</label>
                        <input type="text" id="trace-wid">
                    </div>
                    <div class="form-group">
                        <label for="trace-fpb">완제품 배치 (FPB):</label>
                        <input type="text" id="trace-fpb">
                    </div>
                    <div class="form-group">
                        <label for="trace-barcode">개별 제품 바코드:</label>
                        <input type="text" id="trace-barcode">
                    </div>
                    <div class="form-buttons">
                        <button id="trace-search-btn" class="btn btn-primary">검색</button>
                        <button id="trace-reset-btn" class="btn">초기화</button>
                    </div>
                </div>
            </div>
            <div class="card" style="margin-top: 20px;">
                <h3>검색 결과</h3>
                <div id="trace-results-container" class="table-container"></div>
            </div>
        `;

        const searchBtn = pane.querySelector('#trace-search-btn');
        const resetBtn = pane.querySelector('#trace-reset-btn');
        
        searchBtn.addEventListener('click', performTraceSearch);
        resetBtn.addEventListener('click', () => {
            pane.querySelector('#trace-wid').value = '';
            pane.querySelector('#trace-fpb').value = '';
            pane.querySelector('#trace-barcode').value = '';
            performTraceSearch();
        });

        // 초기 로드 시 전체 세션 표시
        performTraceSearch();
    }

    async function performTraceSearch() {
        const wid = document.getElementById('trace-wid')?.value;
        const fpb = document.getElementById('trace-fpb')?.value;
        const barcode = document.getElementById('trace-barcode')?.value;
        const resultsContainer = document.getElementById('trace-results-container');
        
        if (!resultsContainer) return;
        resultsContainer.innerHTML = '<p>검색 중...</p>';

        try {
            const response = await fetch('/api/trace', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ wid, fpb, barcode }),
            });
            if (!response.ok) throw new Error((await response.json()).error || '검색 실패');
            
            const result = await response.json();
            resultsContainer.innerHTML = '';

            if (result.data.length === 0) {
                resultsContainer.innerHTML = '<p>검색 결과가 없습니다.</p>';
                return;
            }

            let headers, rows;
            if (result.type === 'barcode_trace') {
                headers = ['시간', '공정', '작업자', '이벤트', '상세정보'];
                rows = result.data.map(e => [
                    new Date(e.timestamp).toLocaleString(),
                    e.process,
                    e.worker,
                    e.event,
                    typeof e.details === 'object' ? JSON.stringify(e.details) : e.details
                ]);
            } else { // session_trace
                headers = ['공정', '작업자', '작업 시작', '작업 종료', '품목', '완료수량', 'WID', 'FPB'];
                rows = result.data.map(s => [
                    s.process,
                    s.worker,
                    new Date(s.start_time_dt).toLocaleString(),
                    new Date(s.end_time_dt).toLocaleString(),
                    s.item_display,
                    s.pcs_completed,
                    s.work_order_id,
                    s.product_batch
                ]);
            }
            resultsContainer.appendChild(createTable(headers, rows));

        } catch (error) {
            resultsContainer.innerHTML = `<p style="color: red;">오류: ${error.message}</p>`;
        }
    }


    function renderFullDataTableTab(pane, data) {
        pane.innerHTML = '<h3>상세 데이터</h3>';
        const table = createTable(
            ['날짜', '작업자', '공정', '품목', '작업시간', '완료수량', '오류'],
            data.filtered_sessions_data.map(s => [
                new Date(s.date).toLocaleDateString(),
                s.worker,
                s.process,
                s.item_display,
                formatSeconds(s.work_time),
                s.pcs_completed,
                s.had_error ? '예' : '아니오'
            ])
        );
        const container = document.createElement('div');
        container.className = 'table-container';
        container.appendChild(table);
        pane.appendChild(container);
    }

    function renderComparisonTab(pane, data) {
        if (!data.comparison_data) {
            pane.innerHTML = '<p>비교 데이터를 불러올 수 없습니다. 필터 조건을 확인해주세요.</p>';
            return;
        }
        
        pane.innerHTML = `
            <div class="card">
                <h3>전체 공정 비교 (검사 → 이적 → 포장)</h3>
                <div id="comparison-table-container" class="table-container"></div>
            </div>
            <div class="card" style="margin-top: 20px;">
                <div class="tab-header">
                    <h4>생산량 추이</h4>
                    <div id="comparison-period-radios" class="period-radios">
                        <label><input type="radio" name="comp_period" value="일간" checked><span>일간</span></label>
                        <label><input type="radio" name="comp_period" value="주간"><span>주간</span></label>
                        <label><input type="radio" name="comp_period" value="월간"><span>월간</span></label>
                        <label><input type="radio" name="comp_period" value="연간"><span>연간</span></label>
                    </div>
                </div>
                <div class="comparison-charts-layout">
                    <div><h5>검사실</h5><div class="chart-container"><canvas id="comp-chart-inspection"></canvas></div></div>
                    <div><h5>이적실</h5><div class="chart-container"><canvas id="comp-chart-transfer"></canvas></div></div>
                    <div><h5>포장실</h5><div class="chart-container"><canvas id="comp-chart-packaging"></canvas></div></div>
                </div>
            </div>
        `;

        // 요약 테이블 렌더링
        const summary = data.comparison_data.summary;
        const tableRows = [
            ['총 처리 세트 (Tray)', summary.inspection.total_trays, summary.transfer_standby_trays, summary.transfer.total_trays, summary.packaging_standby_trays, summary.packaging.total_trays],
            ['평균 작업 시간', formatSeconds(summary.inspection.avg_tray_time), '—', formatSeconds(summary.transfer.avg_tray_time), '—', formatSeconds(summary.packaging.avg_tray_time)],
            ['초도 수율 (FPY)', `${(summary.inspection.avg_fpy * 100).toFixed(1)}%`, '—', `${(summary.transfer.avg_fpy * 100).toFixed(1)}%`, '—', `${(summary.packaging.avg_fpy * 100).toFixed(1)}%`],
        ];
        const tableContainer = pane.querySelector('#comparison-table-container');
        const table = createTable(['지표', '검사완료', '이적대기', '이적완료', '포장대기', '포장완료'], tableRows);
        tableContainer.appendChild(table);

        // 차트 렌더링 및 이벤트 리스너
        const trends = data.comparison_data.trends;
        const periodRadios = pane.querySelector('#comparison-period-radios');
        
        const updateCharts = () => {
            const selectedPeriod = periodRadios.querySelector('input:checked').value;
            state.comparison_period = selectedPeriod;
            renderComparisonChart('comp-chart-inspection', '검사실', trends.inspection, selectedPeriod);
            renderComparisonChart('comp-chart-transfer', '이적실', trends.transfer, selectedPeriod);
            renderComparisonChart('comp-chart-packaging', '포장실', trends.packaging, selectedPeriod);
        };

        periodRadios.addEventListener('change', updateCharts);
        updateCharts(); // 초기 차트 렌더링
    }
    
    function renderComparisonChart(canvasId, label, sessions, period) {
        // TODO: 이 함수는 현재 날짜 그룹화 로직에 버그가 있어 데이터가 정확하지 않을 수 있습니다.
        // 특히 '주간', '월간', '연간' 집계 시 표준 시간대 문제 등으로 데이터가 누락될 수 있어 수정이 필요합니다.
        const getPeriodKey = (dateStr, p) => {
            const d = new Date(dateStr);
            if (p === '주간') {
                const day = d.getUTCDay();
                const diff = d.getUTCDate() - day + (day === 0 ? -6 : 1); // Monday as 1st day
                const monday = new Date(d.setUTCDate(diff));
                return monday.toISOString().split('T')[0];
            }
            if (p === '월간') return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
            if (p === '연간') return `${d.getUTCFullYear()}`;
            return d.toISOString().split('T')[0]; // 일간
        };

        const productionByPeriod = sessions.reduce((acc, session) => {
            const key = getPeriodKey(session.date, period);
            acc[key] = (acc[key] || 0) + session.pcs_completed;
            return acc;
        }, {});
        
        const sortedKeys = Object.keys(productionByPeriod).sort();
        
        createChart(canvasId, 'line', {
            labels: sortedKeys,
            datasets: [{
                label: `${label} ${period} 생산량`,
                data: sortedKeys.map(key => productionByPeriod[key]),
                borderColor: 'var(--color-primary)',
                backgroundColor: 'rgba(0, 82, 204, 0.1)',
                fill: true,
                tension: 0.1
            }]
        }, { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } });
    }


    // ########################
    // ### 유틸리티 함수 ###
    // ########################
    function createChart(canvasId, type, data, options) {
        const ctx = document.getElementById(canvasId)?.getContext('2d');
        if (!ctx) return;
        if (state.charts[canvasId]) state.charts[canvasId].destroy();
        state.charts[canvasId] = new Chart(ctx, { type, data, options });
    }
    
    function createTable(headers, rows) {
        const table = document.createElement('table');
        table.className = 'data-table';
        const thead = table.createTHead();
        const headerRow = thead.insertRow();
        headers.forEach(text => {
            const th = document.createElement('th');
            th.textContent = text;
            headerRow.appendChild(th);
        });

        const tbody = table.createTBody();
        rows.forEach(rowData => {
            const row = tbody.insertRow();
            rowData.forEach(cellData => {
                const cell = row.insertCell();
                cell.textContent = cellData;
            });
        });
        return table;
    }
    
    function createCard(title, value, valueClass = '', extraText = '') {
        return `
            <div class="card">
                <h3 class="card-title">${title}</h3>
                <p class="card-value ${valueClass}">${value}</p>
                ${extraText ? `<p class="card-extra">${extraText}</p>` : ''}
            </div>`;
    }

    function formatSeconds(seconds) {
        if (seconds === null || typeof seconds === 'undefined' || isNaN(seconds)) return "N/A";
        if (seconds >= 60) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = Math.round(seconds % 60);
            return `${minutes}분 ${remainingSeconds}초`;
        }
        return `${seconds.toFixed(1)}초`;
    }
    
    function showToast(message) {
        const toast = document.createElement('div');
        Object.assign(toast.style, {
            position: 'fixed', bottom: '20px', left: '50%', transform: 'translateX(-50%)',
            backgroundColor: '#333', color: 'white', padding: '10px 20px',
            borderRadius: '5px', zIndex: '1001', opacity: '0', transition: 'opacity 0.3s'
        });
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.style.opacity = '1', 10);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.addEventListener('transitionend', () => toast.remove());
        }, 3000);
    }

    function sortWorkers(workerData, sortKey) {
        const sorted = [...workerData];
        const keyMap = {
            '이름순': (w) => w.worker,
            '종합 점수 높은 순': (w) => w.overall_score,
            '종합 점수 낮은 순': (w) => w.overall_score,
            '평균 작업 시간 빠른 순': (w) => w.avg_work_time,
            '평균 작업 시간 느린 순': (w) => w.avg_work_time,
            '처리 세트 많은 순': (w) => w.session_count,
        };
        const reverseMap = {
            '종합 점수 높은 순': true,
            '평균 작업 시간 느린 순': true,
            '처리 세트 많은 순': true,
        };

        const sortFn = keyMap[sortKey] || keyMap['종합 점수 높은 순'];
        const reverse = reverseMap[sortKey] || false;

        sorted.sort((a, b) => {
            const valA = sortFn(a);
            const valB = sortFn(b);
            if (typeof valA === 'string') return valA.localeCompare(valB) * (reverse ? -1 : 1);
            return reverse ? valB - valA : valA - valB;
        });
        return sorted;
    }

    function exportToCSV(data, filename) {
        if (data.length === 0) return;
        const headers = Object.keys(data[0]);
        const csvRows = [
            headers.join(','),
            ...data.map(row => 
                headers.map(header => 
                    JSON.stringify(row[header], (key, value) => value === undefined ? '' : value)
                ).join(',')
            )
        ];
        
        const blob = new Blob(['\uFEFF' + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        if (link.download !== undefined) {
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', filename);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    }
});