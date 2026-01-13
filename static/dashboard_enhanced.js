// 향상된 버전 - 차트 + 기간 필터 추가
console.log('🚀 향상된 버전 로드');

window.onerror = function(message, source, lineno, colno, error) {
    console.error('전역 에러:', message, error);
    const errorDiv = document.createElement('div');
    errorDiv.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#dc3545;color:white;padding:15px 30px;border-radius:8px;z-index:99999;box-shadow:0 4px 12px rgba(0,0,0,0.3);';
    errorDiv.innerHTML = '<strong>⚠️ 에러:</strong> ' + message + ' (라인: ' + lineno + ')';
    document.body.appendChild(errorDiv);
    setTimeout(() => errorDiv.remove(), 5000);
    return false;
};

document.addEventListener('DOMContentLoaded', () => {
    console.log('✅ DOMContentLoaded');

    const elements = {
        loadingOverlay: document.getElementById('loading-overlay'),
        processModeRadios: document.getElementById('process-mode-radios'),
        mainTitle: document.getElementById('main-title'),
        tabsContainer: document.querySelector('.tabs'),
        tabContentContainer: document.querySelector('.tab-content'),
    };

    const state = {
        process_mode: '이적실',
        start_date: new Date().toISOString().split('T')[0], // 오늘
        end_date: new Date().toISOString().split('T')[0],   // 오늘
        selected_workers: [],
        full_data: null,
        active_tab: '생산 현황', // 요약과 차트 통합된 탭
        charts: {},
    };

    function getDateDaysAgo(days) {
        const date = new Date();
        date.setDate(date.getDate() - days);
        return date.toISOString().split('T')[0];
    }

    async function loadData() {
        console.log('📡 데이터 로딩 시작...');
        elements.loadingOverlay.classList.remove('hidden');

        try {
            const response = await fetch('/api/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    process_mode: state.process_mode,
                    start_date: state.start_date,
                    end_date: state.end_date,
                    selected_workers: []
                }),
                signal: AbortSignal.timeout(30000) // 30초 타임아웃
            });

            if (!response.ok) throw new Error('API 오류: ' + response.status);

            const data = await response.json();
            console.log('✅ 데이터 수신:', {
                kpis: Object.keys(data.kpis || {}).length,
                workers: data.workers?.length || 0,
                sessions: data.filtered_sessions_data?.length || 0
            });

            state.full_data = data;
            renderDashboard(data);

        } catch (error) {
            console.error('❌ 데이터 로딩 실패:', error);
            elements.tabContentContainer.innerHTML = `
                <div style="padding: 40px; text-align: center;">
                    <h2 style="color: red;">❌ 데이터 로딩 실패</h2>
                    <p>${error.message}</p>
                    <button onclick="location.reload()" style="padding: 10px 20px; margin-top: 20px; cursor: pointer;">새로고침</button>
                </div>
            `;
        } finally {
            elements.loadingOverlay.classList.add('hidden');
        }
    }

    function renderDashboard(data) {
        console.log('📊 대시보드 렌더링 시작...');

        // 제목
        const dateRange = `${state.start_date} ~ ${state.end_date}`;
        elements.mainTitle.textContent = `${state.process_mode} 대시보드 (${dateRange})`;

        // 탭 생성 (공정 모드에 따라 다른 탭 표시)
        elements.tabsContainer.innerHTML = '';
        let tabs;

        if (state.process_mode === '전체 비교') {
            // 전체 비교 모드: 전체 비교 탭만
            tabs = ['전체 비교'];
            state.active_tab = '전체 비교';
        } else {
            // 일반 공정 모드: 생산 현황, 상세 데이터, HR
            tabs = ['생산 현황', '상세 데이터', 'HR'];
            if (!tabs.includes(state.active_tab)) {
                state.active_tab = '생산 현황';
            }
        }

        tabs.forEach(function(tabName) {
            const btn = document.createElement('button');
            btn.className = 'tab-btn' + (tabName === state.active_tab ? ' active' : '');
            btn.textContent = tabName;
            btn.onclick = function() {
                state.active_tab = tabName;
                renderTab(tabName, data);
            };
            elements.tabsContainer.appendChild(btn);
        });

        // 기간 필터 추가
        const filterDiv = document.createElement('div');
        filterDiv.style.cssText = 'display: inline-flex; gap: 8px; margin-left: auto; align-items: center; flex-wrap: wrap;';

        // 현재 선택된 기간 계산
        const currentDays = Math.ceil((new Date(state.end_date) - new Date(state.start_date)) / (1000 * 60 * 60 * 24));

        filterDiv.innerHTML = `
            <button class="btn-preset ${currentDays <= 1 ? 'active' : ''}" data-days="0">오늘</button>
            <button class="btn-preset ${currentDays > 1 && currentDays <= 7 ? 'active' : ''}" data-days="7">1주일</button>
            <button class="btn-preset ${currentDays > 7 && currentDays <= 30 ? 'active' : ''}" data-days="30">1개월</button>
            <button class="btn-preset ${currentDays > 30 && currentDays <= 90 ? 'active' : ''}" data-days="90">분기</button>
            <button class="btn-preset ${currentDays > 90 && currentDays <= 180 ? 'active' : ''}" data-days="180">6개월</button>
            <button class="btn-preset ${currentDays > 180 ? 'active' : ''}" data-days="365">1년</button>
            <button class="btn-preset" id="btn-custom-date">📅 커스텀</button>
        `;
        elements.tabsContainer.appendChild(filterDiv);

        // 커스텀 날짜 선택 패널
        const customDatePanel = document.createElement('div');
        customDatePanel.id = 'custom-date-panel';
        customDatePanel.style.cssText = 'display: none; position: absolute; right: 0; top: 100%; margin-top: 8px; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 1000;';
        customDatePanel.innerHTML = `
            <div style="display: flex; gap: 10px; align-items: center;">
                <div>
                    <label style="display: block; font-size: 12px; color: #666; margin-bottom: 4px;">시작일</label>
                    <input type="date" id="custom-start-date" value="${state.start_date}" style="padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px;">
                </div>
                <div>
                    <label style="display: block; font-size: 12px; color: #666; margin-bottom: 4px;">종료일</label>
                    <input type="date" id="custom-end-date" value="${state.end_date}" style="padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px;">
                </div>
                <button id="apply-custom-date" style="padding: 8px 16px; background: #667eea; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; margin-top: 18px;">적용</button>
            </div>
        `;
        elements.tabsContainer.style.position = 'relative';
        elements.tabsContainer.appendChild(customDatePanel);

        // 기간 필터 이벤트
        filterDiv.querySelectorAll('.btn-preset').forEach(function(btn) {
            btn.onclick = function() {
                // 커스텀 버튼이면 패널 토글
                if (btn.id === 'btn-custom-date') {
                    const panel = document.getElementById('custom-date-panel');
                    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
                    return;
                }

                // 패널 숨기기
                document.getElementById('custom-date-panel').style.display = 'none';

                filterDiv.querySelectorAll('.btn-preset').forEach(function(b) {
                    b.classList.remove('active');
                });
                btn.classList.add('active');

                const days = parseInt(btn.dataset.days);
                if (days === 0) {
                    // 오늘: 오늘 하루만 (시간별 그래프)
                    state.start_date = new Date().toISOString().split('T')[0];
                    state.end_date = new Date().toISOString().split('T')[0];
                } else {
                    // 1주일: 7일 (일별), 1개월: 30일 (일별), 분기: 90일 (주별), 6개월: 180일 (월별), 1년: 365일 (월별)
                    state.start_date = getDateDaysAgo(days);
                    state.end_date = new Date().toISOString().split('T')[0];
                }
                console.log('🔘 기간 필터:', btn.textContent, '→', state.start_date, '~', state.end_date, '(' + (days === 0 ? '1' : days) + '일)');
                loadData();
            };
        });

        // 커스텀 날짜 적용 이벤트
        setTimeout(function() {
            document.getElementById('apply-custom-date').onclick = function() {
                const startDate = document.getElementById('custom-start-date').value;
                const endDate = document.getElementById('custom-end-date').value;

                if (!startDate || !endDate) {
                    alert('시작일과 종료일을 모두 선택해주세요');
                    return;
                }

                if (startDate > endDate) {
                    alert('시작일은 종료일보다 이전이어야 합니다');
                    return;
                }

                state.start_date = startDate;
                state.end_date = endDate;

                // 모든 프리셋 버튼 비활성화
                filterDiv.querySelectorAll('.btn-preset').forEach(function(b) {
                    b.classList.remove('active');
                });
                document.getElementById('btn-custom-date').classList.add('active');

                // 패널 숨기기
                document.getElementById('custom-date-panel').style.display = 'none';

                console.log('📅 커스텀 기간:', state.start_date, '~', state.end_date);
                loadData();
            };

            // 패널 외부 클릭 시 닫기
            document.addEventListener('click', function(e) {
                const panel = document.getElementById('custom-date-panel');
                const customBtn = document.getElementById('btn-custom-date');
                if (panel && customBtn && !panel.contains(e.target) && e.target !== customBtn) {
                    panel.style.display = 'none';
                }
            });
        }, 100);

        // 기본 탭 표시
        renderTab(state.active_tab, data);
        console.log('✅ 대시보드 렌더링 완료');
    }

    function renderTab(tabName, data) {
        console.log('🔄 탭 렌더링:', tabName);

        // 기존 차트 파괴
        Object.values(state.charts).forEach(function(chart) {
            if (chart && chart.destroy) chart.destroy();
        });
        state.charts = {};

        // 탭 활성화 표시
        document.querySelectorAll('.tab-btn').forEach(function(btn) {
            btn.classList.toggle('active', btn.textContent === tabName);
        });

        const container = elements.tabContentContainer;
        container.innerHTML = '';

        if (tabName === '생산 현황') {
            renderProductionDashboard(container, data); // 요약 + 차트 + 작업자 분석 통합
        } else if (tabName === '전체 비교') {
            renderComparisonDashboard(container, data); // 전체 공정 비교
        } else if (tabName === '상세 데이터') {
            renderDetailsWithSearch(container, data); // 검색 기능 추가
        } else if (tabName === 'HR') {
            renderHRDashboard(container, data); // HR 분석 (입사/퇴사)
        }
    }

    // Excel 다운로드 함수 (전역으로 노출)
    window.downloadExcel = function(tabName) {
        const loadingDiv = document.getElementById('loading-overlay');
        loadingDiv.classList.remove('hidden');
        loadingDiv.querySelector('#loading-message').textContent = 'Excel 파일 생성 중...';

        fetch('/api/export_excel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                process_mode: state.process_mode,
                start_date: state.start_date,
                end_date: state.end_date,
                tab: tabName
            })
        })
        .then(function(response) {
            if (!response.ok) throw new Error('Excel 생성 실패');
            return response.blob();
        })
        .then(function(blob) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = '작업분석_' + state.process_mode + '_' + state.start_date + '_' + state.end_date + '.xlsx';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            loadingDiv.classList.add('hidden');
            loadingDiv.querySelector('#loading-message').textContent = '데이터 분석 중...';
        })
        .catch(function(error) {
            alert('Excel 다운로드 실패: ' + error.message);
            loadingDiv.classList.add('hidden');
            loadingDiv.querySelector('#loading-message').textContent = '데이터 분석 중...';
        });
    }

    // 생산 현황 탭 (요약 + 차트 통합)
    function renderProductionDashboard(container, data) {
        const kpis = data.kpis || {};
        const workers = data.worker_data || [];
        const sessions = data.filtered_sessions_data || {};

        const totalPcs = kpis.total_pcs_completed || 0;
        const totalTrays = kpis.total_trays || 0;
        const avgTrayTime = kpis.avg_tray_time || 0;
        const fpy = kpis.avg_fpy || 0;

        container.innerHTML =
            '<div style="padding: 30px;">' +

            // 날짜 범위 + 다운로드 버튼 (한 줄)
            '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">' +
            '<div style="display: flex; align-items: center; gap: 8px; color: #374151;">' +
            '<span style="font-size: 16px;">📅</span>' +
            '<span style="font-size: 15px; font-weight: 600;">' + state.start_date + ' ~ ' + state.end_date + '</span>' +
            '<span style="color: #9ca3af; margin: 0 8px;">|</span>' +
            '<span style="font-size: 14px; color: #6b7280;">' + state.process_mode + '</span>' +
            '</div>' +
            '<button onclick="downloadExcel(\'생산 현황\')" style="padding: 8px 16px; background: #28a745; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px;">' +
            '📥 Excel 다운로드' +
            '</button>' +
            '</div>' +

            // 핵심 생산량 메트릭 (최상단)
            '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">' +

            // 총 생산량
            '<div style="background: white; border-left: 4px solid #2563eb; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">📦 총 생산량' + (state.process_mode === '포장실' ? ' (추정)' : '') + '</div>' +
            '<div style="font-size: 28px; font-weight: bold; color: #111827;">' + totalPcs.toLocaleString() + ' <span style="font-size: 14px; color: #2563eb;">PCS</span></div>' +
            '</div>' +

            // 총 트레이 수
            '<div style="background: white; border-left: 4px solid #7c3aed; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">📋 총 트레이</div>' +
            '<div style="font-size: 28px; font-weight: bold; color: #111827;">' + totalTrays.toLocaleString() + ' <span style="font-size: 14px; color: #7c3aed;">개</span></div>' +
            '</div>' +

            // 평균 작업 시간
            '<div style="background: white; border-left: 4px solid #059669; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">⏱️ 평균 시간</div>' +
            '<div style="font-size: 28px; font-weight: bold; color: #111827;">' + Math.round(avgTrayTime) + ' <span style="font-size: 14px; color: #059669;">초/트레이</span></div>' +
            '</div>' +

            // FPY (품질)
            '<div style="background: white; border-left: 4px solid #dc2626; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">✅ 품질 (FPY)</div>' +
            '<div style="font-size: 28px; font-weight: bold; color: #111827;">' + (fpy * 100).toFixed(1) + '<span style="font-size: 14px; color: #dc2626;">%</span></div>' +
            '</div>' +

            '</div>' +

            // 생산 추이 차트
            '<div style="background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px;">' +
            '<h3 style="margin: 0 0 15px 0; color: #333;">📈 생산 추이</h3>' +
            '<canvas id="productionTrendChart" style="max-height: 300px;"></canvas>' +
            '</div>' +

            // 작업자 분석 테이블 (작업자 2명 이상인 경우만)
            '<div id="worker-analysis-section"></div>' +

            '</div>';

        // 생산 추이 차트 생성 (기간에 따라 자동 집계)
        setTimeout(function() {
            renderProductionChart(data, 'productionTrendChart');
        }, 100);

        // 작업자 분석 테이블 렌더링 (2명 이상일 때만)
        if (workers.length > 1) {
            setTimeout(function() {
                renderWorkerAnalysisTable(document.getElementById('worker-analysis-section'), workers);
            }, 50);
        }
    }

    // 작업자 분석 테이블 (생산현황에 통합)
    function renderWorkerAnalysisTable(container, workers) {
        if (!container || !workers || workers.length < 2) return;

        const sortedWorkers = workers.slice().sort(function(a, b) {
            return (b.total_pcs_completed || 0) - (a.total_pcs_completed || 0);
        });

        const totalPcs = sortedWorkers.reduce(function(sum, w) { return sum + (w.total_pcs_completed || 0); }, 0);
        const avgPcs = totalPcs / sortedWorkers.length;
        const maxPcs = sortedWorkers[0].total_pcs_completed || 0;

        let tableRows = '';
        sortedWorkers.forEach(function(w, index) {
            const pcs = w.total_pcs_completed || 0;
            const percentage = maxPcs > 0 ? (pcs / maxPcs * 100) : 0;
            const medal = index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : '';
            const barColor = index === 0 ? '#ffd700' : index === 1 ? '#c0c0c0' : index === 2 ? '#cd7f32' : '#3b82f6';
            const diff = pcs - avgPcs;
            const diffText = diff >= 0 ? '+' + Math.round(diff).toLocaleString() : Math.round(diff).toLocaleString();
            const diffColor = diff >= 0 ? '#10b981' : '#ef4444';
            const workerId = 'worker-row-' + index;
            const detailId = 'worker-detail-' + index;
            const workerName = (w.worker || '').replace(/'/g, "\\'");

            // 메인 행
            tableRows +=
                '<tr id="' + workerId + '" style="border-bottom: 1px solid #f3f4f6; cursor: pointer; transition: background 0.2s;" onclick="toggleWorkerDetail(\'' + workerName + '\', \'' + detailId + '\', this)" onmouseover="this.style.background=\'#f9fafb\'" onmouseout="this.style.background=\'white\'">' +
                '<td style="padding: 10px 8px; text-align: center; font-weight: bold; color: #6b7280;">' + (medal || (index + 1)) + '</td>' +
                '<td style="padding: 10px 8px; font-weight: 600; color: #3b82f6;">' +
                '<span style="display: inline-flex; align-items: center; gap: 6px;">' +
                '<span class="toggle-icon" style="font-size: 10px; transition: transform 0.2s;">▶</span>' +
                (w.worker || 'N/A') +
                '</span>' +
                '</td>' +
                '<td style="padding: 10px 8px; width: 40%;">' +
                '<div style="background: #f3f4f6; border-radius: 4px; height: 18px; overflow: hidden;">' +
                '<div style="width: ' + percentage + '%; background: ' + barColor + '; height: 100%; border-radius: 4px;"></div>' +
                '</div>' +
                '</td>' +
                '<td style="padding: 10px 8px; text-align: right; font-weight: bold;">' + pcs.toLocaleString() + '</td>' +
                '<td style="padding: 10px 8px; text-align: right; color: ' + diffColor + '; font-size: 13px;">' + diffText + '</td>' +
                '</tr>';

            // 확장 상세 행 (숨김 상태로 시작)
            tableRows +=
                '<tr id="' + detailId + '" style="display: none;">' +
                '<td colspan="5" style="padding: 0; background: #f8fafc;">' +
                '<div class="worker-detail-content" style="padding: 15px 20px;">' +
                '<div style="text-align: center; padding: 20px; color: #6b7280;">로딩 중...</div>' +
                '</div>' +
                '</td>' +
                '</tr>';
        });

        container.innerHTML =
            '<div style="background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px;">' +
            '<div style="padding: 15px 20px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center;">' +
            '<h3 style="margin: 0; font-size: 16px; color: #374151;">🏆 작업자별 생산량 <span style="font-size: 12px; color: #9ca3af; font-weight: normal;">(클릭하여 접기/펼치기)</span></h3>' +
            '<span style="font-size: 13px; color: #6b7280;">평균 ' + Math.round(avgPcs).toLocaleString() + ' PCS</span>' +
            '</div>' +
            '<table style="width: 100%; border-collapse: collapse;">' +
            '<thead><tr style="background: #f9fafb;">' +
            '<th style="padding: 10px 8px; text-align: center; width: 50px; font-size: 12px; color: #6b7280;">순위</th>' +
            '<th style="padding: 10px 8px; text-align: left; width: 100px; font-size: 12px; color: #6b7280;">작업자</th>' +
            '<th style="padding: 10px 8px; text-align: left; font-size: 12px; color: #6b7280;">생산량</th>' +
            '<th style="padding: 10px 8px; text-align: right; width: 90px; font-size: 12px; color: #6b7280;">PCS</th>' +
            '<th style="padding: 10px 8px; text-align: right; width: 70px; font-size: 12px; color: #6b7280;">평균대비</th>' +
            '</tr></thead>' +
            '<tbody>' + tableRows + '</tbody>' +
            '</table>' +
            '</div>';

        // 모든 작업자 상세 정보 자동 펼치기
        setTimeout(function() {
            sortedWorkers.forEach(function(w, index) {
                const detailId = 'worker-detail-' + index;
                const rowElement = document.getElementById('worker-row-' + index);
                const workerName = (w.worker || '').replace(/'/g, "\\'");
                if (rowElement && window.toggleWorkerDetail) {
                    // 순차적으로 로드 (서버 부하 분산)
                    setTimeout(function() {
                        toggleWorkerDetail(workerName, detailId, rowElement);
                    }, index * 100);
                }
            });
        }, 100);
    }

    // HR 대시보드 (입사/퇴사 분석)
    function renderHRDashboard(container, data) {
        const sessions = data.filtered_sessions_data || [];
        const today = new Date();
        const oneWeekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

        // 작업자별 첫 작업일, 마지막 작업일 계산
        const workerStats = {};
        sessions.forEach(function(s) {
            const worker = s.worker;
            if (!worker) return;

            const dateStr = s.start_time_dt || s.date;
            if (!dateStr) return;

            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return;

            if (!workerStats[worker]) {
                workerStats[worker] = {
                    worker: worker,
                    firstDate: date,
                    lastDate: date,
                    sessionCount: 0,
                    totalPcs: 0
                };
            }

            if (date < workerStats[worker].firstDate) {
                workerStats[worker].firstDate = date;
            }
            if (date > workerStats[worker].lastDate) {
                workerStats[worker].lastDate = date;
            }
            workerStats[worker].sessionCount++;
            workerStats[worker].totalPcs += (s.pcs_completed || 0);
        });

        // 재직/퇴사 분류 및 재직기간 계산
        const workers = Object.values(workerStats).map(function(w) {
            const tenure = Math.ceil((w.lastDate - w.firstDate) / (1000 * 60 * 60 * 24)) + 1;
            const isResigned = w.lastDate < oneWeekAgo;
            return {
                worker: w.worker,
                firstDate: w.firstDate,
                lastDate: w.lastDate,
                tenure: tenure,
                sessionCount: w.sessionCount,
                totalPcs: w.totalPcs,
                isResigned: isResigned,
                status: isResigned ? '퇴사' : '재직'
            };
        });

        // 정렬: 재직자 먼저, 그 다음 퇴사자 (각각 마지막 작업일 기준 내림차순)
        workers.sort(function(a, b) {
            if (a.isResigned !== b.isResigned) return a.isResigned ? 1 : -1;
            return b.lastDate - a.lastDate;
        });

        const activeWorkers = workers.filter(function(w) { return !w.isResigned; });
        const resignedWorkers = workers.filter(function(w) { return w.isResigned; });

        // 통계 계산
        const avgTenure = workers.length > 0
            ? Math.round(workers.reduce(function(sum, w) { return sum + w.tenure; }, 0) / workers.length)
            : 0;
        const avgResignedTenure = resignedWorkers.length > 0
            ? Math.round(resignedWorkers.reduce(function(sum, w) { return sum + w.tenure; }, 0) / resignedWorkers.length)
            : 0;

        // 날짜 포맷 함수
        function formatDateShort(date) {
            return date.getFullYear() + '-' +
                   String(date.getMonth() + 1).padStart(2, '0') + '-' +
                   String(date.getDate()).padStart(2, '0');
        }

        // 테이블 행 생성
        let tableRows = '';
        workers.forEach(function(w) {
            const statusColor = w.isResigned ? '#ef4444' : '#10b981';
            const statusBg = w.isResigned ? '#fef2f2' : '#f0fdf4';

            tableRows +=
                '<tr style="border-bottom: 1px solid #f3f4f6;">' +
                '<td style="padding: 12px 10px; font-weight: 600;">' + w.worker + '</td>' +
                '<td style="padding: 12px 10px;">' + formatDateShort(w.firstDate) + '</td>' +
                '<td style="padding: 12px 10px;">' + formatDateShort(w.lastDate) + '</td>' +
                '<td style="padding: 12px 10px; text-align: center; font-weight: bold;">' + w.tenure + '일</td>' +
                '<td style="padding: 12px 10px; text-align: right;">' + w.sessionCount.toLocaleString() + '</td>' +
                '<td style="padding: 12px 10px; text-align: right;">' + w.totalPcs.toLocaleString() + '</td>' +
                '<td style="padding: 12px 10px; text-align: center;">' +
                '<span style="padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; background: ' + statusBg + '; color: ' + statusColor + ';">' + w.status + '</span>' +
                '</td>' +
                '</tr>';
        });

        container.innerHTML =
            '<div style="padding: 20px;">' +

            // 헤더
            '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">' +
            '<div style="display: flex; align-items: center; gap: 8px; color: #374151;">' +
            '<span style="font-size: 16px;">👥</span>' +
            '<span style="font-size: 15px; font-weight: 600;">HR 분석</span>' +
            '<span style="color: #9ca3af; margin: 0 8px;">|</span>' +
            '<span style="font-size: 14px; color: #6b7280;">' + state.process_mode + '</span>' +
            '</div>' +
            '</div>' +

            // KPI 카드
            '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 25px;">' +

            '<div style="background: white; border-left: 4px solid #10b981; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">✅ 재직자</div>' +
            '<div style="font-size: 28px; font-weight: bold; color: #10b981;">' + activeWorkers.length + '<span style="font-size: 14px; color: #6b7280;">명</span></div>' +
            '</div>' +

            '<div style="background: white; border-left: 4px solid #ef4444; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">❌ 퇴사자</div>' +
            '<div style="font-size: 28px; font-weight: bold; color: #ef4444;">' + resignedWorkers.length + '<span style="font-size: 14px; color: #6b7280;">명</span></div>' +
            '</div>' +

            '<div style="background: white; border-left: 4px solid #3b82f6; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">📊 평균 재직기간</div>' +
            '<div style="font-size: 28px; font-weight: bold; color: #3b82f6;">' + avgTenure + '<span style="font-size: 14px; color: #6b7280;">일</span></div>' +
            '</div>' +

            '<div style="background: white; border-left: 4px solid #f59e0b; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">⏱️ 퇴사자 평균 재직</div>' +
            '<div style="font-size: 28px; font-weight: bold; color: #f59e0b;">' + avgResignedTenure + '<span style="font-size: 14px; color: #6b7280;">일</span></div>' +
            '</div>' +

            '</div>' +

            // 안내 문구
            '<div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px 15px; border-radius: 6px; margin-bottom: 20px; font-size: 13px; color: #92400e;">' +
            '💡 1주일 이상 작업 기록이 없는 작업자는 퇴사자로 분류됩니다.' +
            '</div>' +

            // 테이블
            '<div style="background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">' +
            '<div style="padding: 15px 20px; border-bottom: 1px solid #e5e7eb;">' +
            '<h3 style="margin: 0; font-size: 16px; color: #374151;">📋 작업자 현황</h3>' +
            '</div>' +
            '<table style="width: 100%; border-collapse: collapse;">' +
            '<thead><tr style="background: #f9fafb;">' +
            '<th style="padding: 12px 10px; text-align: left; font-size: 12px; color: #6b7280;">작업자</th>' +
            '<th style="padding: 12px 10px; text-align: left; font-size: 12px; color: #6b7280;">첫 작업일</th>' +
            '<th style="padding: 12px 10px; text-align: left; font-size: 12px; color: #6b7280;">마지막 작업일</th>' +
            '<th style="padding: 12px 10px; text-align: center; font-size: 12px; color: #6b7280;">재직기간</th>' +
            '<th style="padding: 12px 10px; text-align: right; font-size: 12px; color: #6b7280;">작업수</th>' +
            '<th style="padding: 12px 10px; text-align: right; font-size: 12px; color: #6b7280;">총 생산량</th>' +
            '<th style="padding: 12px 10px; text-align: center; font-size: 12px; color: #6b7280;">상태</th>' +
            '</tr></thead>' +
            '<tbody>' + tableRows + '</tbody>' +
            '</table>' +
            '</div>' +

            '</div>';
    }

    // 생산 차트 렌더링 (기간에 따라 자동 집계)
    function renderProductionChart(data, canvasId) {
        if (typeof Chart === 'undefined') return;

        const sessions = data.filtered_sessions_data || [];
        const startDate = new Date(state.start_date);
        const endDate = new Date(state.end_date);
        const daysDiff = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1;

        console.log('📊 차트 날짜 범위:', state.start_date, '~', state.end_date, '(' + daysDiff + '일)');

        let labels, values, chartTitle, chartType;
        let dailyData = {};  // 일별 데이터 저장용
        let weeklyData = {};  // 주별 데이터 저장용
        let monthlyData = {};  // 월별 데이터 저장용
        let sortedDates = [];  // 정렬된 날짜 목록

        if (daysDiff <= 1) {
            // 오늘: 시간별 (07~19시는 항상, 나머지는 데이터 있을 때만)
            chartType = 'bar';
            const hourlyData = {};

            // 데이터 집계
            sessions.forEach(function(session) {
                // start_time_dt 또는 start_time 필드 사용
                const startTime = session.start_time_dt || session.start_time;
                if (startTime) {
                    // ISO 형식 또는 HH:MM 형식 모두 처리
                    const timeStr = startTime.indexOf('T') > 0 ? startTime.split('T')[1] : startTime;
                    const hour = parseInt(timeStr.substring(0, 2));
                    if (!isNaN(hour) && hour >= 0 && hour < 24) {
                        if (!hourlyData[hour]) hourlyData[hour] = 0;
                        hourlyData[hour] += (session.pcs_completed || 0);
                    }
                }
            });

            // 07~19시는 항상 포함, 나머지는 데이터가 있을 때만
            const displayHours = [];
            for (let h = 0; h < 24; h++) {
                if ((h >= 7 && h <= 19) || hourlyData[h]) {
                    displayHours.push(h);
                }
            }

            labels = displayHours.map(function(h) { return h + '시'; });
            values = displayHours.map(function(h) { return hourlyData[h] || 0; });
            chartTitle = '📊 시간별 생산량 (오늘)';
        } else if (daysDiff <= 31) {
            // 2-31일: 일별 (1주일 또는 1개월)
            chartType = 'bar';
            dailyData = {};
            sessions.forEach(function(session) {
                const date = session.date ? session.date.split('T')[0] : 'Unknown';
                if (!dailyData[date]) dailyData[date] = 0;
                dailyData[date] += (session.pcs_completed || 0);
            });
            sortedDates = Object.keys(dailyData).sort();
            labels = sortedDates.map(function(d) { return d.substring(5); }); // MM-DD
            values = sortedDates.map(function(date) { return dailyData[date]; });
            chartTitle = '📊 일별 생산량 (' + daysDiff + '일간)';
        } else if (daysDiff <= 91) {
            // 32-91일: 주별 (분기)
            chartType = 'bar';
            weeklyData = {};
            sessions.forEach(function(session) {
                if (session.date) {
                    const date = new Date(session.date);
                    const year = date.getFullYear();
                    const month = date.getMonth() + 1; // 1-12
                    const day = date.getDate();

                    // 해당 월의 몇 번째 주인지 계산 (첫 주는 1일부터 시작)
                    const weekOfMonth = Math.ceil(day / 7);

                    // 라벨: "2026-01 1주" 형식 (정렬을 위해 연도-월 포함)
                    const sortKey = year + '-' + String(month).padStart(2, '0') + '-W' + weekOfMonth;
                    const displayLabel = month + '월 ' + weekOfMonth + '주';

                    if (!weeklyData[sortKey]) {
                        weeklyData[sortKey] = { value: 0, label: displayLabel };
                    }
                    weeklyData[sortKey].value += (session.pcs_completed || 0);
                }
            });
            const sortedWeeks = Object.keys(weeklyData).sort();
            labels = sortedWeeks.map(function(week) { return weeklyData[week].label; });
            values = sortedWeeks.map(function(week) { return weeklyData[week].value; });
            chartTitle = '📊 주별 생산량 (분기, ' + Math.ceil(daysDiff / 7) + '주간)';
        } else {
            // 92일+: 월별 (6개월, 1년 등)
            chartType = 'bar';
            monthlyData = {};
            sessions.forEach(function(session) {
                if (session.date) {
                    const yearMonth = session.date.substring(0, 7);
                    if (!monthlyData[yearMonth]) monthlyData[yearMonth] = 0;
                    monthlyData[yearMonth] += (session.pcs_completed || 0);
                }
            });
            const sortedMonths = Object.keys(monthlyData).sort();
            labels = sortedMonths;
            values = sortedMonths.map(function(month) { return monthlyData[month]; });
            const monthCount = Math.ceil(daysDiff / 30);
            const period = monthCount <= 6 ? '6개월' : monthCount <= 12 ? '1년' : monthCount + '개월';
            chartTitle = '📊 월별 생산량 (' + period + ', ' + monthCount + '개월간)';
        }

        // 과거 평균값 계산 (각 시간대/일별/주차/월별로 과거 데이터의 평균)
        const historicalSummary = data.historical_summary || {};
        const historicalAverages = historicalSummary.averages || {};

        let avgLine = [];
        let avgLabel = '';
        let totalAvg = 0;

        if (daysDiff <= 1) {
            // 시간별: 각 시간대의 과거 평균 사용
            const hourlyAvg = historicalAverages.hourly_pcs || {};
            avgLine = labels.map(function(label) {
                const hour = parseInt(label);  // "7시" -> 7
                return hourlyAvg[hour] || 0;
            });
            totalAvg = avgLine.reduce(function(a, b) { return a + b; }, 0) / (avgLine.length || 1);
            avgLabel = '과거 시간대별 평균 (' + totalAvg.toFixed(0) + ' PCS)';
        } else if (daysDiff <= 31) {
            // 일별: 각 요일의 과거 평균 사용 (월-일: 0-6)
            const weekdayAvg = historicalAverages.weekday_pcs || {};
            avgLine = sortedDates.map(function(dateStr) {
                const date = new Date(dateStr);
                const weekday = date.getDay();  // 0=일요일, 1=월요일, ..., 6=토요일
                // JS의 getDay()는 일요일이 0, 월요일이 1
                // Python은 월요일이 0, 일요일이 6
                // 변환: JS getDay() -> Python weekday
                const pythonWeekday = (weekday + 6) % 7;  // 0(일)->6, 1(월)->0, 2(화)->1, ...
                return weekdayAvg[pythonWeekday] || 0;
            });
            totalAvg = avgLine.reduce(function(a, b) { return a + b; }, 0) / (avgLine.length || 1);
            avgLabel = '과거 요일별 평균 (' + totalAvg.toFixed(0) + ' PCS)';
        } else if (daysDiff <= 91) {
            // 주별: 각 주차의 과거 평균 사용 (1-5주차)
            const weekOfMonthAvg = historicalAverages.week_of_month_pcs || {};
            avgLine = Object.keys(weeklyData).sort().map(function(weekKey) {
                // weekKey 형식: "2026-01-W3" -> 3주차
                const weekNum = parseInt(weekKey.split('-W')[1]);
                return weekOfMonthAvg[weekNum] || 0;
            });
            totalAvg = avgLine.reduce(function(a, b) { return a + b; }, 0) / (avgLine.length || 1);
            avgLabel = '과거 주차별 평균 (' + totalAvg.toFixed(0) + ' PCS)';
        } else {
            // 월별: 각 월의 과거 평균 사용 (1-12월)
            const monthlyAvg = historicalAverages.monthly_pcs || {};
            avgLine = Object.keys(monthlyData).sort().map(function(yearMonth) {
                const month = parseInt(yearMonth.split('-')[1]);  // "2025-12" -> 12
                return monthlyAvg[month] || 0;
            });
            totalAvg = avgLine.reduce(function(a, b) { return a + b; }, 0) / (avgLine.length || 1);
            avgLabel = '과거 월별 평균 (' + totalAvg.toFixed(0) + ' PCS)';
        }

        console.log('📊 차트 타입:', chartType, '| 제목:', chartTitle, '| 데이터 포인트:', labels.length, '| 과거 평균:', avgLabel);

        const ctx = document.getElementById(canvasId);
        if (ctx) {
            state.charts[canvasId] = new Chart(ctx, {
                type: chartType,
                data: {
                    labels: labels,
                    datasets: [{
                        label: '생산량 (PCS)' + (state.process_mode === '포장실' ? ' - 추정치' : ''),
                        data: values,
                        backgroundColor: 'rgba(102, 126, 234, 0.7)',
                        borderColor: '#667eea',
                        borderWidth: 2,
                        type: 'bar'
                    }, {
                        label: avgLabel,
                        data: avgLine,
                        type: 'line',
                        borderColor: '#ff6b6b',
                        backgroundColor: 'rgba(255, 107, 107, 0.1)',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        fill: false,
                        pointRadius: 4,
                        pointBackgroundColor: '#ff6b6b',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        tension: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                usePointStyle: true,
                                padding: 15,
                                font: { size: 12 }
                            }
                        },
                        title: {
                            display: true,
                            text: chartTitle,
                            font: { size: 16, weight: 'bold' }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: { color: '#666' },
                            title: { display: true, text: 'PCS' }
                        },
                        x: {
                            ticks: { color: '#666' }
                        }
                    }
                }
            });
        }
    }

    function renderChartTab(container, data) {
        container.innerHTML =
            '<div style="padding: 20px;">' +
            '<h2 style="margin-bottom: 20px;">📈 생산량 차트</h2>' +
            '<div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">' +
            '<canvas id="productionChart" style="max-height: 400px;"></canvas>' +
            '</div>' +
            '</div>';

        // Chart.js 로드 확인
        if (typeof Chart === 'undefined') {
            container.querySelector('div').innerHTML += '<p style="color: red; margin-top: 20px;">⚠️ Chart.js가 로드되지 않았습니다.</p>';
            return;
        }

        // 날짜 범위 계산
        const startDate = new Date(state.start_date);
        const endDate = new Date(state.end_date);
        const daysDiff = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1;

        console.log('📊 차트 날짜 범위:', state.start_date, '~', state.end_date, '(' + daysDiff + '일)');

        // 데이터 준비
        const sessions = data.filtered_sessions_data || [];
        let labels, values, chartTitle, aggregationType;

        if (daysDiff <= 1) {
            // 오늘: 시간별 차트
            aggregationType = 'hourly';
            const hourlyData = {};
            for (let h = 0; h < 24; h++) {
                hourlyData[h] = 0;
            }
            sessions.forEach(function(session) {
                if (session.start_time) {
                    const hour = parseInt(session.start_time.substring(0, 2));
                    hourlyData[hour] = (hourlyData[hour] || 0) + 1;
                }
            });
            labels = Object.keys(hourlyData).map(function(h) { return h + '시'; });
            values = Object.values(hourlyData);
            chartTitle = '시간별 생산 세션 수';
        } else if (daysDiff <= 31) {
            // 2-31일: 일별 차트
            aggregationType = 'daily';
            const dailyData = {};
            sessions.forEach(function(session) {
                const date = session.date ? session.date.split('T')[0] : 'Unknown';
                dailyData[date] = (dailyData[date] || 0) + 1;
            });
            const sortedDates = Object.keys(dailyData).sort();
            labels = sortedDates;
            values = sortedDates.map(function(date) { return dailyData[date]; });
            chartTitle = '일별 생산 세션 수 (' + daysDiff + '일)';
        } else if (daysDiff <= 91) {
            // 32-91일: 주별 차트
            aggregationType = 'weekly';
            const weeklyData = {};
            sessions.forEach(function(session) {
                if (session.date) {
                    const date = new Date(session.date);
                    const weekNum = getWeekNumber(date);
                    const weekKey = date.getFullYear() + '-W' + weekNum;
                    weeklyData[weekKey] = (weeklyData[weekKey] || 0) + 1;
                }
            });
            const sortedWeeks = Object.keys(weeklyData).sort();
            labels = sortedWeeks;
            values = sortedWeeks.map(function(week) { return weeklyData[week]; });
            chartTitle = '주별 생산 세션 수 (' + Math.ceil(daysDiff / 7) + '주)';
        } else {
            // 92일 이상: 월별 차트
            aggregationType = 'monthly';
            const monthlyData = {};
            sessions.forEach(function(session) {
                if (session.date) {
                    const yearMonth = session.date.substring(0, 7); // YYYY-MM
                    monthlyData[yearMonth] = (monthlyData[yearMonth] || 0) + 1;
                }
            });
            const sortedMonths = Object.keys(monthlyData).sort();
            labels = sortedMonths;
            values = sortedMonths.map(function(month) { return monthlyData[month]; });
            chartTitle = '월별 생산 세션 수 (' + Math.ceil(daysDiff / 30) + '개월)';
        }

        console.log('📊 차트 타입:', aggregationType, '| 데이터 포인트:', labels.length);

        // 차트 생성 (비동기로 브라우저 멈춤 방지)
        setTimeout(function() {
            try {
                const ctx = document.getElementById('productionChart');
                if (!ctx) {
                    console.error('Canvas 요소를 찾을 수 없습니다');
                    return;
                }

                state.charts.production = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: '일별 세션 수',
                            data: values,
                            backgroundColor: 'rgba(54, 162, 235, 0.6)',
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: {
                            legend: { display: true },
                            title: {
                                display: true,
                                text: chartTitle
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: { display: true, text: '세션 수' }
                            },
                            x: {
                                title: { display: true, text: '날짜' }
                            }
                        }
                    }
                });
                console.log('✅ 차트 생성 완료');
            } catch (error) {
                console.error('❌ 차트 생성 실패:', error);
                container.querySelector('div').innerHTML += '<p style="color: red; margin-top: 20px;">⚠️ 차트 생성 실패: ' + error.message + '</p>';
            }
        }, 100);
    }

    function renderWorkersTab(container, data) {
        const workers = data.worker_data || [];
        const sortedWorkers = workers.slice().sort(function(a, b) {
            return (b.total_pcs_completed || 0) - (a.total_pcs_completed || 0);
        });

        const workerRows = sortedWorkers.slice(0, 50).map(function(w, index) {
            const rank = index + 1;
            const rankColor = rank === 1 ? '#ffd700' : rank === 2 ? '#c0c0c0' : rank === 3 ? '#cd7f32' : '#f8f9fa';
            return '<tr style="border-bottom: 1px solid #ddd;">' +
                '<td style="padding: 10px; background: ' + rankColor + '; font-weight: bold;">' + rank + '</td>' +
                '<td style="padding: 10px;"><strong>' + (w.worker || 'N/A') + '</strong></td>' +
                '<td style="padding: 10px; text-align: right;"><strong>' + (w.total_pcs_completed || 0).toLocaleString() + '</strong></td>' +
                '<td style="padding: 10px; text-align: right;">' + formatSeconds(w.avg_work_time || 0) + '</td>' +
                '<td style="padding: 10px; text-align: right;">' + (w.session_count || 0) + '</td>' +
                '<td style="padding: 10px; text-align: right;">' + ((w.first_pass_yield || 0) * 100).toFixed(1) + '%</td>' +
                '</tr>';
        }).join('');

        container.innerHTML =
            '<div style="padding: 20px;">' +
            '<h2 style="margin-bottom: 20px;">👥 작업자 순위 (' + workers.length + '명)</h2>' +
            '<div style="overflow-x: auto;">' +
            '<table style="width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">' +
            '<thead><tr style="background: #007bff; color: white;">' +
            '<th style="padding: 12px; text-align: left;">순위</th>' +
            '<th style="padding: 12px; text-align: left;">작업자</th>' +
            '<th style="padding: 12px; text-align: right;">완료 PCS</th>' +
            '<th style="padding: 12px; text-align: right;">평균시간</th>' +
            '<th style="padding: 12px; text-align: right;">세션 수</th>' +
            '<th style="padding: 12px; text-align: right;">FPY</th>' +
            '</tr></thead>' +
            '<tbody>' + workerRows + '</tbody>' +
            '</table>' +
            '</div>' +
            (workers.length > 50 ? '<p style="margin-top: 15px; color: #666;">...외 ' + (workers.length - 50) + '명</p>' : '') +
            '</div>';
    }

    function renderDetailsTab(container, data) {
        const sessions = data.filtered_sessions_data || [];
        const recentSessions = sessions.slice(0, 100);

        const sessionRows = recentSessions.map(function(s) {
            return '<tr style="border-bottom: 1px solid #eee;">' +
                '<td style="padding: 8px;">' + formatDate(s.date) + '</td>' +
                '<td style="padding: 8px;"><strong>' + (s.worker || 'N/A') + '</strong></td>' +
                '<td style="padding: 8px;">' + formatTime(s.start_time) + '</td>' +
                '<td style="padding: 8px;">' + formatTime(s.end_time) + '</td>' +
                '<td style="padding: 8px; text-align: right;">' + formatSeconds(s.work_time) + '</td>' +
                '<td style="padding: 8px; text-align: right;">' + (s.pcs_completed || 0) + '</td>' +
                '</tr>';
        }).join('');

        container.innerHTML =
            '<div style="padding: 20px;">' +
            '<h2 style="margin-bottom: 20px;">📋 상세 데이터 (최근 100개)</h2>' +
            '<div style="overflow-x: auto;">' +
            '<table style="width: 100%; border-collapse: collapse; font-size: 13px; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">' +
            '<thead><tr style="background: #28a745; color: white;">' +
            '<th style="padding: 10px;">날짜</th>' +
            '<th style="padding: 10px;">작업자</th>' +
            '<th style="padding: 10px;">시작</th>' +
            '<th style="padding: 10px;">종료</th>' +
            '<th style="padding: 10px; text-align: right;">소요시간</th>' +
            '<th style="padding: 10px; text-align: right;">PCS</th>' +
            '</tr></thead>' +
            '<tbody>' + sessionRows + '</tbody>' +
            '</table>' +
            '</div>' +
            (sessions.length > 100 ? '<p style="margin-top: 15px; color: #666;">총 ' + sessions.length + '개 세션 중 100개 표시</p>' : '') +
            '</div>';
    }

    // 유틸리티 함수들
    function formatKpiLabel(key) {
        const labels = {
            'avg_defect_rate': '불량률',
            'avg_fpy': 'FPY',
            'avg_latency': '지연시간',
            'avg_pcs_per_tray': '트레이당 PCS',
            'avg_tray_time': '평균 트레이 시간',
            'total_errors': '총 에러',
            'total_pcs_completed': '총 완료 PCS',
            'total_trays': '총 트레이',
            'weekly_avg_errors': '주간 평균 에러'
        };
        return labels[key] || key;
    }

    function formatValue(value) {
        if (typeof value === 'number') {
            if (value > 1000) return value.toLocaleString();
            return value.toFixed(2);
        }
        return value || 'N/A';
    }

    function formatSeconds(seconds) {
        if (!seconds || seconds === 0) return '0초';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return mins > 0 ? mins + '분 ' + secs + '초' : secs + '초';
    }

    function formatDate(dateStr) {
        if (!dateStr) return 'N/A';
        return dateStr.split('T')[0];
    }

    function formatTime(timeStr) {
        if (!timeStr) return 'N/A';
        return timeStr.substring(0, 8);
    }

    // 날짜+시간 포맷팅 함수 (YYYY-MM-DD HH:MM:SS 형식, 시간 없으면 날짜만)
    function formatDateTime(dateStr) {
        if (!dateStr) return 'N/A';
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return 'N/A';
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const hours = date.getHours();
            const mins = date.getMinutes();
            const secs = date.getSeconds();
            // 시간이 00:00:00이면 날짜만 표시
            if (hours === 0 && mins === 0 && secs === 0) {
                return year + '-' + month + '-' + day;
            }
            return year + '-' + month + '-' + day + ' ' +
                   String(hours).padStart(2, '0') + ':' +
                   String(mins).padStart(2, '0') + ':' +
                   String(secs).padStart(2, '0');
        } catch (e) {
            return dateStr;
        }
    }

    // 주차 계산 함수
    function getWeekNumber(date) {
        const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
        const dayNum = d.getUTCDay() || 7;
        d.setUTCDate(d.getUTCDate() + 4 - dayNum);
        const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
        return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    }

    // 공정 변경 이벤트
    elements.processModeRadios.addEventListener('change', function(e) {
        state.process_mode = e.target.value;
        loadData();
    });

    // 전체 비교 탭 (통일된 비즈니스 스타일)
    function renderComparisonDashboard(container, data) {
        const comparison = data.comparison_data;

        if (!comparison) {
            container.innerHTML = '<div style="padding: 40px; text-align: center; color: #6b7280;"><p>전체 비교 데이터를 불러오는 중입니다...</p><p style="font-size: 12px; margin-top: 10px;">공정 모드를 "전체 비교"로 변경하세요.</p></div>';
            return;
        }

        // 선택한 날짜 범위의 데이터 사용 (날짜 필터 반영)
        const period = comparison.summary_period || {};

        // 전체 합계 계산
        const totalTrays = (period.inspection?.total_trays || 0) + (period.transfer?.total_trays || 0) + (period.packaging?.total_trays || 0);
        const totalPcs = (period.inspection?.total_pcs_completed || 0) + (period.transfer?.total_pcs_completed || 0) + (period.packaging?.total_pcs_completed || 0);

        let html = '';

        html += '<div style="padding: 30px;">';

        // 날짜 범위 (한 줄)
        html += '<div style="display: flex; align-items: center; gap: 8px; color: #374151; margin-bottom: 20px;">';
        html += '<span style="font-size: 16px;">📅</span>';
        html += '<span style="font-size: 15px; font-weight: 600;">' + state.start_date + ' ~ ' + state.end_date + '</span>';
        html += '<span style="color: #9ca3af; margin: 0 8px;">|</span>';
        html += '<span style="font-size: 14px; color: #6b7280;">' + state.process_mode + '</span>';
        html += '</div>';

        // 상단 KPI 카드 (다른 탭과 동일한 스타일)
        html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px;">';

        // 전체 트레이
        html += '<div style="background: white; border-left: 6px solid #2563eb; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">';
        html += '<div style="font-size: 14px; color: #6b7280; font-weight: 500; margin-bottom: 10px;">📋 전체 트레이</div>';
        html += '<div style="font-size: 36px; font-weight: bold; color: #111827; margin-bottom: 5px;">' + totalTrays.toLocaleString() + '</div>';
        html += '<div style="font-size: 13px; color: #2563eb; font-weight: 600;">개 처리</div>';
        html += '</div>';

        // 전체 생산량
        html += '<div style="background: white; border-left: 6px solid #10b981; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">';
        html += '<div style="font-size: 14px; color: #6b7280; font-weight: 500; margin-bottom: 10px;">📦 전체 생산량</div>';
        html += '<div style="font-size: 36px; font-weight: bold; color: #111827; margin-bottom: 5px;">' + totalPcs.toLocaleString() + '</div>';
        html += '<div style="font-size: 13px; color: #10b981; font-weight: 600;">PCS 완료</div>';
        html += '</div>';

        // 이적 대기
        const transferStandby = period.transfer_standby_trays || 0;
        const transferStandbyColor = transferStandby > 0 ? '#ef4444' : '#10b981';
        html += '<div style="background: white; border-left: 6px solid ' + transferStandbyColor + '; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">';
        html += '<div style="font-size: 14px; color: #6b7280; font-weight: 500; margin-bottom: 10px;">⏳ 이적 대기</div>';
        html += '<div style="font-size: 36px; font-weight: bold; color: ' + transferStandbyColor + '; margin-bottom: 5px;">' + transferStandby + '</div>';
        html += '<div style="font-size: 13px; color: ' + transferStandbyColor + '; font-weight: 600;">트레이 대기중</div>';
        html += '</div>';

        // 포장 대기
        const packagingStandby = period.packaging_standby_trays || 0;
        const packagingStandbyColor = packagingStandby > 0 ? '#ef4444' : '#10b981';
        html += '<div style="background: white; border-left: 6px solid ' + packagingStandbyColor + '; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">';
        html += '<div style="font-size: 14px; color: #6b7280; font-weight: 500; margin-bottom: 10px;">⏳ 포장 대기</div>';
        html += '<div style="font-size: 36px; font-weight: bold; color: ' + packagingStandbyColor + '; margin-bottom: 5px;">' + packagingStandby + '</div>';
        html += '<div style="font-size: 13px; color: ' + packagingStandbyColor + '; font-weight: 600;">트레이 대기중</div>';
        html += '</div>';

        html += '</div>';

        // 공정별 현황 카드
        html += '<div style="background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 25px;">';
        html += '<h3 style="margin: 0 0 25px 0; font-size: 18px; font-weight: 700; color: #111827;">🏭 공정별 생산 현황</h3>';

        html += '<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px;">';

        // 검사실 카드
        html += '<div style="background: #f8fafc; border-radius: 12px; padding: 25px; border: 1px solid #e2e8f0;">';
        html += '<div style="display: flex; align-items: center; margin-bottom: 20px;">';
        html += '<div style="width: 48px; height: 48px; background: #3b82f6; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-right: 15px;">';
        html += '<span style="font-size: 24px;">🔍</span>';
        html += '</div>';
        html += '<div>';
        html += '<div style="font-size: 18px; font-weight: 700; color: #111827;">검사실</div>';
        html += '<div style="font-size: 13px; color: #6b7280;">STAGE 01</div>';
        html += '</div>';
        html += '</div>';
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">';
        html += '<div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">';
        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 5px;">트레이</div>';
        html += '<div style="font-size: 28px; font-weight: 700; color: #3b82f6;">' + (period.inspection?.total_trays || 0).toLocaleString() + '</div>';
        html += '</div>';
        html += '<div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">';
        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 5px;">PCS</div>';
        html += '<div style="font-size: 28px; font-weight: 700; color: #3b82f6;">' + (period.inspection?.total_pcs_completed || 0).toLocaleString() + '</div>';
        html += '</div>';
        html += '</div>';
        html += '<div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 13px; color: #6b7280;">';
        html += '<span>평균: ' + (period.inspection?.avg_tray_time?.toFixed(0) || 0) + '초</span>';
        html += '<span>FPY: ' + (period.inspection?.avg_fpy ? (period.inspection.avg_fpy * 100).toFixed(1) : 0) + '%</span>';
        html += '</div>';
        html += '</div>';

        // 이적실 카드
        html += '<div style="background: #f8fafc; border-radius: 12px; padding: 25px; border: 1px solid #e2e8f0;">';
        html += '<div style="display: flex; align-items: center; margin-bottom: 20px;">';
        html += '<div style="width: 48px; height: 48px; background: #8b5cf6; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-right: 15px;">';
        html += '<span style="font-size: 24px;">📦</span>';
        html += '</div>';
        html += '<div>';
        html += '<div style="font-size: 18px; font-weight: 700; color: #111827;">이적실</div>';
        html += '<div style="font-size: 13px; color: #6b7280;">STAGE 02</div>';
        html += '</div>';
        html += '</div>';
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">';
        html += '<div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">';
        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 5px;">트레이</div>';
        html += '<div style="font-size: 28px; font-weight: 700; color: #8b5cf6;">' + (period.transfer?.total_trays || 0).toLocaleString() + '</div>';
        html += '</div>';
        html += '<div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">';
        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 5px;">PCS</div>';
        html += '<div style="font-size: 28px; font-weight: 700; color: #8b5cf6;">' + (period.transfer?.total_pcs_completed || 0).toLocaleString() + '</div>';
        html += '</div>';
        html += '</div>';
        html += '<div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 13px; color: #6b7280;">';
        html += '<span>평균: ' + (period.transfer?.avg_tray_time?.toFixed(0) || 0) + '초</span>';
        html += '<span>FPY: ' + (period.transfer?.avg_fpy ? (period.transfer.avg_fpy * 100).toFixed(1) : 0) + '%</span>';
        html += '</div>';
        html += '</div>';

        // 포장실 카드
        html += '<div style="background: #f8fafc; border-radius: 12px; padding: 25px; border: 1px solid #e2e8f0;">';
        html += '<div style="display: flex; align-items: center; margin-bottom: 20px;">';
        html += '<div style="width: 48px; height: 48px; background: #06b6d4; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-right: 15px;">';
        html += '<span style="font-size: 24px;">🎁</span>';
        html += '</div>';
        html += '<div>';
        html += '<div style="font-size: 18px; font-weight: 700; color: #111827;">포장실</div>';
        html += '<div style="font-size: 13px; color: #6b7280;">STAGE 03</div>';
        html += '</div>';
        html += '</div>';
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">';
        html += '<div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">';
        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 5px;">트레이</div>';
        html += '<div style="font-size: 28px; font-weight: 700; color: #06b6d4;">' + (period.packaging?.total_trays || 0).toLocaleString() + '</div>';
        html += '</div>';
        html += '<div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">';
        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 5px;">PCS <span style="color: #f59e0b; font-size: 10px;">(추정)</span></div>';
        html += '<div style="font-size: 28px; font-weight: 700; color: #06b6d4;">' + (period.packaging?.total_pcs_completed || 0).toLocaleString() + '</div>';
        html += '</div>';
        html += '</div>';
        html += '<div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 13px; color: #6b7280;">';
        html += '<span>평균: ' + (period.packaging?.avg_tray_time?.toFixed(0) || 0) + '초</span>';
        html += '<span>FPY: ' + (period.packaging?.avg_fpy ? (period.packaging.avg_fpy * 100).toFixed(1) : 0) + '%</span>';
        html += '</div>';
        html += '</div>';

        html += '</div>';
        html += '</div>';

        // 대기 현황 상세
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">';

        // 이적 대기 상세
        const transferStandbyPcs = period.transfer_standby_pcs || 0;
        html += '<div style="background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">';
        html += '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">';
        html += '<h4 style="margin: 0; font-size: 16px; font-weight: 700; color: #111827;">📥 이적 대기 현황</h4>';
        if (transferStandby > 0) {
            html += '<span style="background: #fef2f2; color: #ef4444; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">대기중</span>';
        } else {
            html += '<span style="background: #f0fdf4; color: #10b981; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">정상</span>';
        }
        html += '</div>';
        html += '<div style="font-size: 13px; color: #6b7280; margin-bottom: 15px;">검사 완료 → 이적 대기</div>';
        html += '<div style="display: flex; gap: 15px;">';
        html += '<div style="flex: 1; text-align: center; background: #f8fafc; padding: 20px; border-radius: 8px;">';
        html += '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">트레이</div>';
        html += '<div style="font-size: 32px; font-weight: 700; color: ' + transferStandbyColor + ';">' + transferStandby + '</div>';
        html += '</div>';
        html += '<div style="flex: 1; text-align: center; background: #f8fafc; padding: 20px; border-radius: 8px;">';
        html += '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">PCS</div>';
        html += '<div style="font-size: 32px; font-weight: 700; color: ' + transferStandbyColor + ';">' + transferStandbyPcs.toLocaleString() + '</div>';
        html += '</div>';
        html += '</div>';
        html += '</div>';

        // 포장 대기 상세
        const packagingStandbyPcs = period.packaging_standby_pcs || 0;
        html += '<div style="background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">';
        html += '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">';
        html += '<h4 style="margin: 0; font-size: 16px; font-weight: 700; color: #111827;">📤 포장 대기 현황</h4>';
        if (packagingStandby > 0) {
            html += '<span style="background: #fef2f2; color: #ef4444; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">대기중</span>';
        } else {
            html += '<span style="background: #f0fdf4; color: #10b981; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">정상</span>';
        }
        html += '</div>';
        html += '<div style="font-size: 13px; color: #6b7280; margin-bottom: 15px;">이적 완료 → 포장 대기</div>';
        html += '<div style="display: flex; gap: 15px;">';
        html += '<div style="flex: 1; text-align: center; background: #f8fafc; padding: 20px; border-radius: 8px;">';
        html += '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">트레이</div>';
        html += '<div style="font-size: 32px; font-weight: 700; color: ' + packagingStandbyColor + ';">' + packagingStandby + '</div>';
        html += '</div>';
        html += '<div style="flex: 1; text-align: center; background: #f8fafc; padding: 20px; border-radius: 8px;">';
        html += '<div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">PCS</div>';
        html += '<div style="font-size: 32px; font-weight: 700; color: ' + packagingStandbyColor + ';">' + packagingStandbyPcs.toLocaleString() + '</div>';
        html += '</div>';
        html += '</div>';
        html += '</div>';

        html += '</div>';

        html += '</div>';

        container.innerHTML = html;
    }

    // 작업자 분석 탭 (생산량 비교 막대 그래프)
    function renderWorkersWithRadar(container, data) {
        const workers = data.worker_data || [];

        if (!workers || workers.length === 0) {
            container.innerHTML = '<div style="padding: 40px; text-align: center; color: #6b7280;"><p>작업자 데이터가 없습니다.</p></div>';
            return;
        }

        const sortedWorkers = workers.slice().sort(function(a, b) {
            return (b.total_pcs_completed || 0) - (a.total_pcs_completed || 0);
        });

        // 통계 계산
        const totalPcs = sortedWorkers.reduce(function(sum, w) { return sum + (w.total_pcs_completed || 0); }, 0);
        const totalTrays = sortedWorkers.reduce(function(sum, w) { return sum + (w.session_count || 0); }, 0);
        const avgPcs = totalPcs / sortedWorkers.length;
        const maxPcs = sortedWorkers[0].total_pcs_completed || 0;
        const minPcs = sortedWorkers[sortedWorkers.length - 1].total_pcs_completed || 0;

        // 테이블 행 HTML 생성
        let tableRows = '';
        sortedWorkers.forEach(function(w, index) {
            const pcs = w.total_pcs_completed || 0;
            const percentage = maxPcs > 0 ? (pcs / maxPcs * 100) : 0;
            const medal = index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : '';
            const barColor = index === 0 ? '#ffd700' : index === 1 ? '#c0c0c0' : index === 2 ? '#cd7f32' : '#3b82f6';
            const diff = pcs - avgPcs;
            const diffText = diff >= 0 ? '+' + Math.round(diff).toLocaleString() : Math.round(diff).toLocaleString();
            const diffColor = diff >= 0 ? '#10b981' : '#ef4444';

            tableRows +=
                '<tr style="border-bottom: 1px solid #f3f4f6;">' +
                '<td style="padding: 12px 8px; text-align: center; font-weight: bold; color: #6b7280;">' + (medal || (index + 1)) + '</td>' +
                '<td style="padding: 12px 8px; font-weight: 600;">' + (w.worker || 'N/A') + '</td>' +
                '<td style="padding: 12px 8px; width: 40%;">' +
                '<div style="background: #f3f4f6; border-radius: 4px; height: 20px; overflow: hidden;">' +
                '<div style="width: ' + percentage + '%; background: ' + barColor + '; height: 100%; border-radius: 4px; transition: width 0.3s;"></div>' +
                '</div>' +
                '</td>' +
                '<td style="padding: 12px 8px; text-align: right; font-weight: bold; font-size: 15px;">' + pcs.toLocaleString() + '</td>' +
                '<td style="padding: 12px 8px; text-align: right; color: ' + diffColor + '; font-size: 13px;">' + diffText + '</td>' +
                '</tr>';
        });

        container.innerHTML =
            '<div style="padding: 20px;">' +

            // 헤더: 날짜 + 요약 + 다운로드 (한 줄)
            '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">' +
            '<div style="display: flex; align-items: center; gap: 20px;">' +
            '<span style="color: #6b7280;">' + state.start_date + ' ~ ' + state.end_date + '</span>' +
            '<span style="font-weight: bold;">' + sortedWorkers.length + '명</span>' +
            '<span style="font-weight: bold; color: #3b82f6;">' + totalPcs.toLocaleString() + ' PCS</span>' +
            '<span style="color: #6b7280;">평균 ' + Math.round(avgPcs).toLocaleString() + '</span>' +
            '</div>' +
            '<button onclick="downloadExcel(\'작업자 분석\')" style="padding: 6px 12px; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;">📥 Excel</button>' +
            '</div>' +

            // 테이블
            '<div style="background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">' +
            '<table style="width: 100%; border-collapse: collapse;">' +
            '<thead><tr style="background: #f9fafb; border-bottom: 2px solid #e5e7eb;">' +
            '<th style="padding: 10px 8px; text-align: center; width: 50px;">순위</th>' +
            '<th style="padding: 10px 8px; text-align: left; width: 80px;">작업자</th>' +
            '<th style="padding: 10px 8px; text-align: left;">생산량</th>' +
            '<th style="padding: 10px 8px; text-align: right; width: 100px;">PCS</th>' +
            '<th style="padding: 10px 8px; text-align: right; width: 80px;">평균대비</th>' +
            '</tr></thead>' +
            '<tbody>' + tableRows + '</tbody>' +
            '</table>' +
            '</div>' +

            '</div>';

        // 기존 차트가 있으면 파괴 (더 이상 Chart.js 사용 안함)
        if (state.charts.workerComparisonChart) {
            state.charts.workerComparisonChart.destroy();
            state.charts.workerComparisonChart = null;
        }
    }

    // 상세 데이터 탭 (검색 기능 포함)
    function renderDetailsWithSearch(container, data) {
        const sessions = data.filtered_sessions_data || [];

        // 상세 검색 상태
        if (!state.detailSearch) {
            state.detailSearch = {
                worker: '',
                product: '',
                dateFrom: '',
                dateTo: '',
                minPcs: '',
                maxPcs: ''
            };
        }

        container.innerHTML =
            '<div style="padding: 20px;">' +

            // 날짜 범위 + 다운로드 버튼 (한 줄)
            '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">' +
            '<div style="display: flex; align-items: center; gap: 8px; color: #374151;">' +
            '<span style="font-size: 16px;">📅</span>' +
            '<span style="font-size: 15px; font-weight: 600;">' + state.start_date + ' ~ ' + state.end_date + '</span>' +
            '<span style="color: #9ca3af; margin: 0 8px;">|</span>' +
            '<span style="font-size: 14px; color: #6b7280;">' + state.process_mode + '</span>' +
            '</div>' +
            '<button onclick="downloadExcel(\'상세 데이터\')" style="padding: 8px 16px; background: #28a745; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px;">' +
            '📥 Excel 다운로드' +
            '</button>' +
            '</div>' +

            // 검색 필터 섹션
            '<div style="background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px;">' +
            '<h3 style="margin: 0 0 15px 0;">🔍 상세 검색</h3>' +
            '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">' +

            '<div>' +
            '<label style="display: block; margin-bottom: 5px; font-size: 12px; color: #666;">작업자</label>' +
            '<input type="text" id="filter-worker" placeholder="작업자 이름" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">' +
            '</div>' +

            '<div>' +
            '<label style="display: block; margin-bottom: 5px; font-size: 12px; color: #666;">품목</label>' +
            '<input type="text" id="filter-product" placeholder="품목명/코드" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">' +
            '</div>' +

            '<div>' +
            '<label style="display: block; margin-bottom: 5px; font-size: 12px; color: #666;">시작 날짜</label>' +
            '<input type="date" id="filter-date-from" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">' +
            '</div>' +

            '<div>' +
            '<label style="display: block; margin-bottom: 5px; font-size: 12px; color: #666;">종료 날짜</label>' +
            '<input type="date" id="filter-date-to" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">' +
            '</div>' +

            '<div>' +
            '<label style="display: block; margin-bottom: 5px; font-size: 12px; color: #666;">최소 생산량</label>' +
            '<input type="number" id="filter-min-pcs" placeholder="최소 PCS" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">' +
            '</div>' +

            '<div>' +
            '<label style="display: block; margin-bottom: 5px; font-size: 12px; color: #666;">최대 생산량</label>' +
            '<input type="number" id="filter-max-pcs" placeholder="최대 PCS" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px;">' +
            '</div>' +

            '</div>' +

            '<div style="margin-top: 15px; display: flex; gap: 10px;">' +
            '<button id="apply-filter-btn" style="padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold;">🔍 검색</button>' +
            '<button id="reset-filter-btn" style="padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer;">초기화</button>' +
            '</div>' +

            '</div>' +

            // 데이터 테이블
            '<div style="background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">' +
            '<h3 style="margin: 0 0 15px 0;">📊 상세 데이터 (<span id="detail-count">0</span>건)</h3>' +
            '<div id="detail-table-container" style="overflow-x: auto;"></div>' +
            '</div>' +

            '</div>';

        // 필터 적용 함수
        function applyDetailFilter() {
            state.detailSearch.worker = document.getElementById('filter-worker').value.trim();
            state.detailSearch.product = document.getElementById('filter-product').value.trim();
            state.detailSearch.dateFrom = document.getElementById('filter-date-from').value;
            state.detailSearch.dateTo = document.getElementById('filter-date-to').value;
            state.detailSearch.minPcs = document.getElementById('filter-min-pcs').value;
            state.detailSearch.maxPcs = document.getElementById('filter-max-pcs').value;

            let filtered = sessions;

            // 작업자 필터
            if (state.detailSearch.worker) {
                filtered = filtered.filter(function(s) {
                    return (s.worker || '').includes(state.detailSearch.worker);
                });
            }

            // 품목 필터
            if (state.detailSearch.product) {
                filtered = filtered.filter(function(s) {
                    const itemCode = s.item_code || '';
                    const itemName = s.item_name || '';
                    const itemDisplay = s.item_display || '';
                    return itemCode.includes(state.detailSearch.product) ||
                           itemName.includes(state.detailSearch.product) ||
                           itemDisplay.includes(state.detailSearch.product);
                });
            }

            // 날짜 필터
            if (state.detailSearch.dateFrom) {
                filtered = filtered.filter(function(s) {
                    return s.date >= state.detailSearch.dateFrom;
                });
            }
            if (state.detailSearch.dateTo) {
                filtered = filtered.filter(function(s) {
                    return s.date <= state.detailSearch.dateTo;
                });
            }

            // 생산량 필터
            if (state.detailSearch.minPcs) {
                const minPcs = parseInt(state.detailSearch.minPcs);
                filtered = filtered.filter(function(s) {
                    return (s.pcs_completed || 0) >= minPcs;
                });
            }
            if (state.detailSearch.maxPcs) {
                const maxPcs = parseInt(state.detailSearch.maxPcs);
                filtered = filtered.filter(function(s) {
                    return (s.pcs_completed || 0) <= maxPcs;
                });
            }

            // 테이블 렌더링 (최대 200개)
            renderDetailTable(filtered.slice(0, 200));
            document.getElementById('detail-count').textContent = filtered.length;
        }

        // 테이블 렌더링
        function renderDetailTable(filteredSessions) {
            if (filteredSessions.length === 0) {
                document.getElementById('detail-table-container').innerHTML =
                    '<p style="text-align: center; color: #999; padding: 40px;">검색 결과가 없습니다</p>';
                return;
            }

            let tableHtml = '<table style="width: 100%; border-collapse: collapse; font-size: 13px;">' +
                '<thead><tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">' +
                '<th style="padding: 10px; text-align: left;">날짜</th>' +
                '<th style="padding: 10px; text-align: left;">작업자</th>' +
                '<th style="padding: 10px; text-align: left;">품목</th>' +
                '<th style="padding: 10px; text-align: right;">생산량</th>' +
                '<th style="padding: 10px; text-align: right;">작업시간</th>' +
                '<th style="padding: 10px; text-align: right;">FPY</th>' +
                '<th style="padding: 10px; text-align: center;">불량</th>' +
                '</tr></thead><tbody>';

            filteredSessions.forEach(function(s, index) {
                const bgColor = index % 2 === 0 ? '#ffffff' : '#f8f9fa';
                tableHtml += '<tr style="background: ' + bgColor + '; border-bottom: 1px solid #dee2e6;">' +
                    '<td style="padding: 8px;">' + formatDateTime(s.start_time_dt || s.date) + '</td>' +
                    '<td style="padding: 8px;">' + (s.worker || 'N/A') + '</td>' +
                    '<td style="padding: 8px;">' + (s.item_display || s.item_name || 'N/A') + '</td>' +
                    '<td style="padding: 8px; text-align: right; font-weight: bold;">' + (s.pcs_completed || 0) + ' PCS</td>' +
                    '<td style="padding: 8px; text-align: right;">' + formatSeconds(s.work_time || 0) + '</td>' +
                    '<td style="padding: 8px; text-align: right;">' + ((s.first_pass_yield || 0) * 100).toFixed(1) + '%</td>' +
                    '<td style="padding: 8px; text-align: center;">' + (s.had_error ? '❌' : '✅') + '</td>' +
                    '</tr>';
            });

            tableHtml += '</tbody></table>';

            if (filteredSessions.length >= 200) {
                tableHtml += '<p style="text-align: center; color: #999; margin-top: 15px; font-size: 12px;">* 최대 200개까지만 표시됩니다</p>';
            }

            document.getElementById('detail-table-container').innerHTML = tableHtml;
        }

        // 이벤트 바인딩
        setTimeout(function() {
            document.getElementById('apply-filter-btn').onclick = applyDetailFilter;
            document.getElementById('reset-filter-btn').onclick = function() {
                document.getElementById('filter-worker').value = '';
                document.getElementById('filter-product').value = '';
                document.getElementById('filter-date-from').value = '';
                document.getElementById('filter-date-to').value = '';
                document.getElementById('filter-min-pcs').value = '';
                document.getElementById('filter-max-pcs').value = '';
                state.detailSearch = {};
                applyDetailFilter();
            };

            // 초기 데이터 표시
            applyDetailFilter();
        }, 100);
    }

    // 바코드 검색 모달 열기/닫기
    window.openBarcodeModal = function() {
        document.getElementById('barcode-modal').style.display = 'flex';
        document.body.style.overflow = 'hidden'; // 배경 스크롤 방지
    };

    window.closeBarcodeModal = function() {
        document.getElementById('barcode-modal').style.display = 'none';
        document.body.style.overflow = 'auto';
    };

    // ESC 키로 모달 닫기
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('barcode-modal');
            if (modal && modal.style.display === 'flex') {
                closeBarcodeModal();
            }
        }
    });

    // 바코드 검색 기능 초기화
    function initBarcodeSearch() {
        const barcodeInput = document.getElementById('barcode-input');
        const searchBtn = document.getElementById('search-barcode-btn');
        const modalBody = document.getElementById('barcode-modal-body');

        if (!barcodeInput || !searchBtn) {
            console.log('⚠️ 바코드 검색 요소 없음');
            return;
        }

        searchBtn.onclick = async function() {
            const barcode = barcodeInput.value.trim();
            if (!barcode) {
                alert('바코드를 입력해주세요');
                return;
            }

            // 모달 열기
            openBarcodeModal();
            modalBody.innerHTML = '<div style="text-align: center; padding: 40px;"><div style="font-size: 48px; margin-bottom: 15px;">🔍</div><p style="font-size: 16px; color: #6b7280;">검색 중...</p></div>';

            try {
                const response = await fetch('/api/barcode_search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ barcode: barcode })
                });

                const result = await response.json();

                if (!response.ok || result.error) {
                    throw new Error(result.error || '검색 실패');
                }

                // 결과 표시 (비즈니스 스타일)
                if (result.found) {
                    let html = '';

                    // 상단 헤더: 바코드 + 발견 상태
                    html += '<div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px; border-top: 4px solid #059669;">';
                    html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">';
                    html += '<div>';
                    html += '<h3 style="margin: 0; color: #111827; font-size: 18px;">🔍 ' + result.barcode + '</h3>';
                    // 실제 바코드가 다른 경우 표시
                    if (result.actual_barcode && result.actual_barcode !== result.barcode) {
                        html += '<div style="font-size: 12px; color: #6b7280; margin-top: 5px;">실제 바코드: <span style="font-family: monospace; color: #2563eb;">' + result.actual_barcode + '</span></div>';
                    }
                    html += '</div>';
                    html += '<span style="background: #d1fae5; color: #065f46; padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 600;">✅ 발견됨</span>';
                    html += '</div>';

                    // 핵심 정보 그리드 (작업자, 공정, 품목, 시간)
                    html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 15px;">';

                    // 작업자
                    if (result.scan_info && result.scan_info.worker) {
                        html += '<div style="background: #f9fafb; padding: 12px; border-radius: 6px; border-left: 3px solid #2563eb;">';
                        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">작업자</div>';
                        html += '<div style="font-size: 16px; font-weight: bold; color: #111827;">' + result.scan_info.worker + '</div>';
                        html += '</div>';
                    }

                    // 공정
                    if (result.scan_info && result.scan_info.process) {
                        html += '<div style="background: #f9fafb; padding: 12px; border-radius: 6px; border-left: 3px solid #7c3aed;">';
                        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">공정</div>';
                        html += '<div style="font-size: 16px; font-weight: bold; color: #111827;">' + result.scan_info.process + '</div>';
                        html += '</div>';
                    }

                    // 품목
                    if (result.tray_info && result.tray_info.item_code) {
                        html += '<div style="background: #f9fafb; padding: 12px; border-radius: 6px; border-left: 3px solid #059669;">';
                        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">품목 코드</div>';
                        html += '<div style="font-size: 16px; font-weight: bold; color: #111827;">' + result.tray_info.item_code + '</div>';
                        html += '</div>';
                    }

                    // 스캔 개수
                    if (result.tray_info && result.tray_info.scan_count) {
                        html += '<div style="background: #f9fafb; padding: 12px; border-radius: 6px; border-left: 3px solid #dc2626;">';
                        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">스캔 개수</div>';
                        html += '<div style="font-size: 16px; font-weight: bold; color: #111827;">' + result.tray_info.scan_count + ' / ' + (result.tray_info.tray_capacity || 'N/A') + '</div>';
                        html += '</div>';
                    }

                    html += '</div>';
                    html += '</div>';

                    // 타임라인 (시각적으로 개선)
                    if (result.timeline) {
                        html += '<div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px;">';
                        html += '<div style="font-size: 14px; font-weight: 600; color: #111827; margin-bottom: 15px;">⏱️ 작업 타임라인</div>';

                        // 타임라인 시각화
                        html += '<div style="display: flex; align-items: center; gap: 10px; position: relative;">';

                        // 시작
                        html += '<div style="flex: 1; text-align: center;">';
                        html += '<div style="width: 40px; height: 40px; background: #dbeafe; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px; font-size: 18px;">🚀</div>';
                        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 3px;">시작</div>';
                        html += '<div style="font-size: 12px; font-weight: 600; color: #111827;">' + (result.timeline.start || 'N/A') + '</div>';
                        html += '</div>';

                        // 화살표
                        html += '<div style="flex-shrink: 0; color: #d1d5db; font-size: 20px;">→</div>';

                        // 스캔
                        html += '<div style="flex: 1; text-align: center;">';
                        html += '<div style="width: 40px; height: 40px; background: #fef3c7; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px; font-size: 18px;">📱</div>';
                        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 3px;">스캔</div>';
                        html += '<div style="font-size: 12px; font-weight: 600; color: #111827;">' + (result.timeline.scan || 'N/A') + '</div>';
                        html += '</div>';

                        // 화살표
                        html += '<div style="flex-shrink: 0; color: #d1d5db; font-size: 20px;">→</div>';

                        // 완료
                        html += '<div style="flex: 1; text-align: center;">';
                        html += '<div style="width: 40px; height: 40px; background: #d1fae5; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px; font-size: 18px;">✅</div>';
                        html += '<div style="font-size: 11px; color: #6b7280; margin-bottom: 3px;">완료</div>';
                        html += '<div style="font-size: 12px; font-weight: 600; color: #111827;">' + (result.timeline.complete || 'N/A') + '</div>';
                        html += '</div>';

                        html += '</div>';
                        html += '</div>';
                    }

                    // 상세 정보 (2열 그리드)
                    html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">';

                    // 스캔 상세 정보
                    if (result.scan_info) {
                        html += '<div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 4px solid #2563eb;">';
                        html += '<div style="font-size: 14px; font-weight: 600; color: #2563eb; margin-bottom: 12px;">📋 스캔 정보</div>';
                        html += '<div style="display: flex; flex-direction: column; gap: 8px;">';
                        html += '<div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f3f4f6;"><span style="color: #6b7280; font-size: 13px;">스캔 시간</span><span style="font-weight: 600; color: #111827; font-size: 13px;">' + (result.scan_info.scan_time || 'N/A') + '</span></div>';
                        html += '<div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f3f4f6;"><span style="color: #6b7280; font-size: 13px;">상태</span><span style="font-weight: 600; color: #111827; font-size: 13px;">' + (result.scan_info.status || 'N/A') + '</span></div>';
                        html += '</div>';
                        html += '</div>';
                    }

                    // 트레이 상세 정보
                    if (result.tray_info) {
                        html += '<div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 4px solid #059669;">';
                        html += '<div style="font-size: 14px; font-weight: 600; color: #059669; margin-bottom: 12px;">📦 트레이 정보</div>';
                        html += '<div style="display: flex; flex-direction: column; gap: 8px;">';
                        html += '<div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f3f4f6;"><span style="color: #6b7280; font-size: 13px;">작업 시간</span><span style="font-weight: 600; color: #111827; font-size: 13px;">' + (result.tray_info.work_time || 'N/A') + '</span></div>';
                        html += '<div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f3f4f6;"><span style="color: #6b7280; font-size: 13px;">바코드 위치</span><span style="font-weight: 600; color: #111827; font-size: 13px;">' + (result.tray_info.barcode_position || 'N/A') + '</span></div>';
                        html += '<div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f3f4f6;"><span style="color: #6b7280; font-size: 13px;">에러</span><span style="font-weight: 600; color: ' + (result.tray_info.error_count > 0 ? '#dc2626' : '#059669') + '; font-size: 13px;">' + (result.tray_info.error_count || '없음') + '</span></div>';
                        html += '<div style="display: flex; justify-content: space-between; padding: 8px 0;"><span style="color: #6b7280; font-size: 13px;">완료 시간</span><span style="font-weight: 600; color: #111827; font-size: 13px;">' + (result.tray_info.complete_time || 'N/A') + '</span></div>';
                        html += '</div>';
                        html += '</div>';
                    }

                    html += '</div>';

                    modalBody.innerHTML = html;
                } else {
                    // 미발견 상태
                    let html = '<div style="background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; border-top: 4px solid #dc2626;">';
                    html += '<div style="font-size: 48px; margin-bottom: 15px;">❌</div>';
                    html += '<h3 style="margin: 0 0 10px 0; color: #111827; font-size: 18px;">바코드를 찾을 수 없습니다</h3>';
                    html += '<div style="font-size: 14px; color: #6b7280; margin-bottom: 15px;">' + result.barcode + '</div>';
                    html += '<div style="background: #fef2f2; color: #991b1b; padding: 12px; border-radius: 6px; font-size: 13px;">해당 바코드는 시스템에 등록되지 않았거나<br>데이터베이스에 기록이 없습니다.</div>';
                    html += '</div>';
                    modalBody.innerHTML = html;
                }

            } catch (error) {
                modalBody.innerHTML = '<div style="padding: 40px; text-align: center;"><div style="font-size: 48px; margin-bottom: 15px;">⚠️</div><div style="padding: 15px; background: #fef2f2; color: #991b1b; border-radius: 8px; font-size: 14px;">오류: ' + error.message + '</div></div>';
            }
        };

        // Enter 키 지원
        barcodeInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                searchBtn.click();
            }
        });

        console.log('✅ 바코드 검색 기능 활성화');
    }

    // 모바일 메뉴 토글
    function initMobileMenu() {
        const menuBtn = document.getElementById('mobile-menu-btn');
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.getElementById('sidebar-overlay');

        if (!menuBtn || !sidebar || !overlay) return;

        menuBtn.onclick = function() {
            sidebar.classList.toggle('mobile-open');
            overlay.classList.toggle('active');
        };

        overlay.onclick = function() {
            sidebar.classList.remove('mobile-open');
            overlay.classList.remove('active');
        };

        // 사이드바 내부 클릭 시에도 닫기 (필터 선택 후)
        sidebar.querySelectorAll('input[type="radio"]').forEach(function(radio) {
            radio.addEventListener('change', function() {
                if (window.innerWidth <= 768) {
                    setTimeout(function() {
                        sidebar.classList.remove('mobile-open');
                        overlay.classList.remove('active');
                    }, 300);
                }
            });
        });
    }

    // 초기 로딩
    console.log('🚀 초기 데이터 로딩 시작');
    loadData();

    // 바코드 검색 초기화
    initBarcodeSearch();

    // 모바일 메뉴 초기화
    initMobileMenu();

    // 작업자 상세 토글 관련
    window.workerDetailCharts = {};

    window.toggleWorkerDetail = async function(workerName, detailId, rowElement) {
        const detailRow = document.getElementById(detailId);
        if (!detailRow) return;

        const toggleIcon = rowElement.querySelector('.toggle-icon');
        const isVisible = detailRow.style.display !== 'none';

        if (isVisible) {
            // 접기
            detailRow.style.display = 'none';
            if (toggleIcon) toggleIcon.style.transform = 'rotate(0deg)';

            // 차트 정리
            if (window.workerDetailCharts[detailId]) {
                if (window.workerDetailCharts[detailId].hourly) {
                    window.workerDetailCharts[detailId].hourly.destroy();
                }
                if (window.workerDetailCharts[detailId].daily) {
                    window.workerDetailCharts[detailId].daily.destroy();
                }
                delete window.workerDetailCharts[detailId];
            }
            return;
        }

        // 펼치기
        detailRow.style.display = 'table-row';
        if (toggleIcon) toggleIcon.style.transform = 'rotate(90deg)';

        const contentDiv = detailRow.querySelector('.worker-detail-content');
        contentDiv.innerHTML = '<div style="text-align: center; padding: 30px; color: #6b7280;"><div class="loading-spinner" style="display: inline-block; width: 30px; height: 30px; border: 3px solid #e5e7eb; border-top-color: #3b82f6; border-radius: 50%; animation: spin 1s linear infinite;"></div><p style="margin-top: 10px;">데이터 로딩 중...</p></div>';

        try {
            const response = await fetch('/api/worker_hourly', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    worker: workerName,
                    start_date: state.start_date,
                    end_date: state.end_date,
                    process_mode: state.process_mode
                })
            });

            if (!response.ok) throw new Error('API 오류');

            const data = await response.json();

            if (data.error) {
                contentDiv.innerHTML = '<div style="text-align: center; padding: 20px; color: #ef4444;">' + data.error + '</div>';
                return;
            }

            const s = data.summary || {};
            const hourlyChartId = 'hourly-chart-' + detailId;
            const dailyChartId = 'daily-chart-' + detailId;

            // 상세 콘텐츠 렌더링
            contentDiv.innerHTML =
                '<div style="border-top: 2px solid #3b82f6;">' +
                // 요약 통계
                '<div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; padding: 15px; background: #f8fafc; border-bottom: 1px solid #e5e7eb;">' +
                '<div style="text-align: center;"><div style="font-size: 18px; font-weight: bold; color: #1d4ed8;">' + (s.total_pcs || 0).toLocaleString() + '</div><div style="font-size: 10px; color: #6b7280;">총 생산량</div></div>' +
                '<div style="text-align: center;"><div style="font-size: 18px; font-weight: bold; color: #16a34a;">' + (s.avg_daily_pcs || 0).toLocaleString() + '</div><div style="font-size: 10px; color: #6b7280;">일평균</div></div>' +
                '<div style="text-align: center;"><div style="font-size: 18px; font-weight: bold; color: #ca8a04;">' + (s.total_sessions || 0).toLocaleString() + '</div><div style="font-size: 10px; color: #6b7280;">세션수</div></div>' +
                '<div style="text-align: center;"><div style="font-size: 18px; font-weight: bold; color: #a855f7;">' + (s.first_pass_yield || 0) + '%</div><div style="font-size: 10px; color: #6b7280;">초도수율</div></div>' +
                '<div style="text-align: center;"><div style="font-size: 18px; font-weight: bold; color: #ea580c;">' + (s.avg_work_time || 0) + '초</div><div style="font-size: 10px; color: #6b7280;">평균작업시간</div></div>' +
                '<div style="text-align: center;"><div style="font-size: 18px; font-weight: bold; color: #57534e;">' + (s.num_days || 0) + '일</div><div style="font-size: 10px; color: #6b7280;">작업일수</div></div>' +
                '</div>' +
                // 차트 영역
                '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; padding: 15px;">' +
                '<div style="background: white; border-radius: 6px; padding: 12px; border: 1px solid #e5e7eb;">' +
                '<div style="font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 8px;">시간대별 평균 생산량</div>' +
                '<div style="height: 150px;"><canvas id="' + hourlyChartId + '"></canvas></div>' +
                '</div>' +
                '<div style="background: white; border-radius: 6px; padding: 12px; border: 1px solid #e5e7eb;">' +
                '<div style="font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 8px;">일별 생산량</div>' +
                '<div style="height: 150px;"><canvas id="' + dailyChartId + '"></canvas></div>' +
                '</div>' +
                '</div>' +
                '</div>';

            // 차트 인스턴스 저장 객체 초기화
            window.workerDetailCharts[detailId] = {};

            // 시간대별 차트
            const hourlyCtx = document.getElementById(hourlyChartId);
            if (hourlyCtx && data.hourly_data && data.hourly_data.values) {
                window.workerDetailCharts[detailId].hourly = new Chart(hourlyCtx.getContext('2d'), {
                    type: 'bar',
                    data: {
                        labels: data.hourly_data.labels,
                        datasets: [{
                            data: data.hourly_data.values,
                            backgroundColor: 'rgba(59, 130, 246, 0.7)',
                            borderColor: 'rgba(59, 130, 246, 1)',
                            borderWidth: 1,
                            borderRadius: 3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, ticks: { font: { size: 10 } } },
                            x: { ticks: { font: { size: 9 }, maxRotation: 0 } }
                        }
                    }
                });
            }

            // 일별 차트
            const dailyCtx = document.getElementById(dailyChartId);
            if (dailyCtx && data.daily_data && data.daily_data.length > 0) {
                const dailyLabels = data.daily_data.map(d => d.date.slice(5)); // MM-DD 형식
                const dailyValues = data.daily_data.map(d => d.pcs);

                window.workerDetailCharts[detailId].daily = new Chart(dailyCtx.getContext('2d'), {
                    type: 'line',
                    data: {
                        labels: dailyLabels,
                        datasets: [{
                            data: dailyValues,
                            borderColor: 'rgba(16, 185, 129, 1)',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.3,
                            pointRadius: 3,
                            pointBackgroundColor: 'rgba(16, 185, 129, 1)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, ticks: { font: { size: 10 } } },
                            x: { ticks: { font: { size: 9 }, maxRotation: 45, minRotation: 45 } }
                        }
                    }
                });
            }

        } catch (error) {
            console.error('작업자 데이터 로딩 실패:', error);
            contentDiv.innerHTML = '<div style="text-align: center; padding: 20px; color: #ef4444;">데이터 로딩 실패: ' + error.message + '</div>';
        }
    };

    console.log('✅ 작업자 상세 토글 기능 초기화 완료');
});

console.log('✅ 향상된 버전 스크립트 로드 완료');
