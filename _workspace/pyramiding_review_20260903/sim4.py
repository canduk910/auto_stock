import json, statistics, math
d=json.load(open('sim2.json'))
for strat,rows in d.items():
    act=[r['actual'] for r in rows]
    n=len(act); m=statistics.mean(act); sd=statistics.stdev(act)
    se=sd/math.sqrt(n)
    print(f"== {strat}: n={n} 평균수익={m:.2f}N 표준편차={sd:.2f}N 표준오차={se:.2f}N  95%CI=[{m-1.96*se:.2f}, {m+1.96*se:.2f}]N")
    # TE>0 를 95% 신뢰로 확인하려면 필요한 표본 (효과크기 0.2N 가정)
    for eff in (0.2,0.3,0.5):
        need=math.ceil((1.96*sd/eff)**2)
        print(f"   진짜 기대값 +{eff}N 을 95% 신뢰로 검출하려면 n≈{need} 왕복 필요")
    st=[r for r in rows if r['half4_SF'][2]=='stopped']
    ex=[r for r in rows if r['half4_SF'][2]!='stopped']
    print(f"   1/2N 4유닛: 스탑청산 {len(st)}건 평균 {statistics.mean([r['half4_SF'][0] for r in st]):.2f}N (최악 {min(r['half4_SF'][0] for r in st):.2f}N)")
    if ex: print(f"              정상청산 {len(ex)}건 평균 {statistics.mean([r['half4_SF'][0] for r in ex]):.2f}N (최고 {max(r['half4_SF'][0] for r in ex):.2f}N)")
    from collections import Counter
    print(f"   최종 유닛수 분포: {dict(sorted(Counter(r['half4_SF'][1] for r in rows).items()))}")
    # 개별 최악/최고
    worst=min(rows,key=lambda r:r['half4_SF'][0]); best=max(rows,key=lambda r:r['half4_SF'][0])
    print(f"   최악: {worst['name']}({worst['ticker']}) 실측 {worst['actual']:.2f}N → 피라미딩 {worst['half4_SF'][0]:.2f}N ({worst['half4_SF'][1]}유닛)")
    print(f"   최고: {best['name']}({best['ticker']}) 실측 {best['actual']:.2f}N → 피라미딩 {best['half4_SF'][0]:.2f}N ({best['half4_SF'][1]}유닛)")
    print()
