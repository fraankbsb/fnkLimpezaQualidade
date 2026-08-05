@echo off
setlocal enabledelayedexpansion

:: ================================================
::   RAIZ
:: ================================================
set "RAIZ=D:\fnkSocialMidia\fnkPerfis"
set "PASTA_VIDEOS=VIDEOS RECORTADOS"
set "PASTA_LIMPOS=VIDEOS LIMPOS"

:: ================================================
::   CODEC E QUALIDADE
:: ================================================
set "CODEC_VIDEO=libx264"
set "BITRATE_VIDEO=6M"
set "PRESET=medium"
set "BITRATE_AUDIO=192k"
set "FPS_SAIDA=60"

:: ================================================
::   METADADOS APPLE
:: ================================================
set "META_MAKE=Apple"
set "META_MODEL=iPhone 15 Pro Max"
set "META_SOFTWARE=17.5.1"
set "META_CREATION=2024-09-15T10:23:44"

:: ================================================
::   UNICACAO
:: ================================================
set "UNIC_TRIM_START=0.1"
set "UNIC_SPEED=1.005"
set "UNIC_PITCH=1.02"
set "UNIC_HUE=2"
set "UNIC_NOISE=1"
set "UNIC_DEFLICKER=1"
set "UNIC_LENS=1"
set "UNIC_FADE=0.3"
set "UNIC_CROP_TOPO=0"
set "UNIC_EQ_AUDIO=1"

:: ================================================
::   BLUR DE MARCA D'AGUA (@usuario)
:: ================================================
:: Como a posicao do @usuario varia entre videos, borra uma
:: faixa inteira em cima e embaixo (onde watermarks costumam ficar)
:: em vez de tentar acertar uma posicao fixa.
set "UNIC_BLUR_MARCA=1"
set "BLUR_FAIXA_BAIXO=0.22"
set "BLUR_FAIXA_TOPO=0.08"
set "BLUR_FORCA=25"

:: ================================================
::   Verifica FFmpeg
:: ================================================
ffmpeg -version >nul 2>&1
if !errorlevel! NEQ 0 (
    echo  [ERRO] FFmpeg nao encontrado!
    pause
    exit /b 1
)

:: ================================================
::   MENU NICHO
:: ================================================
:menu_nicho
cls
echo.
echo  ============================================
echo    PROCESSADOR DE VIDEOS - QUALIDADE E LIMPEZA
echo    iPhone 15 Pro Max  ^|  H.264  ^|  6Mbps  ^|  60fps
echo  ============================================
echo.
echo   Raiz: !RAIZ!
echo.
echo   Selecione o NICHO:
echo.

set "num_nicho=0"
for /f "usebackq delims=" %%D in (`dir /b /ad "!RAIZ!" 2^>nul`) do (
    set /a num_nicho+=1
    set "NICHO_!num_nicho!=%%D"
    echo   !num_nicho! - %%D
)

if !num_nicho!==0 (
    echo  [ERRO] Nenhum nicho encontrado em !RAIZ!
    pause
    exit /b 1
)

echo.
echo   0 - Sair
echo.
echo  --------------------------------------------
set /p "esc_nicho=  Digite o numero do nicho: "

if "!esc_nicho!"=="0" exit /b 0

set "NICHO_SEL="
if defined NICHO_!esc_nicho! set "NICHO_SEL=!NICHO_%esc_nicho%!"
if "!NICHO_SEL!"=="" (
    echo  Opcao invalida.
    timeout /t 1 /nobreak >nul
    goto menu_nicho
)

:: ================================================
::   MENU PERFIL DENTRO DO NICHO
:: ================================================
:menu_perfil
cls
echo.
echo  ============================================
echo    NICHO: !NICHO_SEL!
echo  ============================================
echo.
echo   Selecione o PERFIL ^(ou multiplos separados por virgula^):
echo   Ex: 1   ou   1,3,5
echo.

set "num_perfil=0"
for /f "usebackq delims=" %%D in (`dir /b /ad "!RAIZ!\!NICHO_SEL!" 2^>nul`) do (
    set /a num_perfil+=1
    set "PERFIL_!num_perfil!=%%D"

    :: Verifica se tem VIDEOS RECORTADOS
    if exist "!RAIZ!\!NICHO_SEL!\%%D\!PASTA_VIDEOS!" (
        echo   !num_perfil! - %%D  [tem videos]
    ) else (
        echo   !num_perfil! - %%D  [sem pasta de videos]
    )
)

if !num_perfil!==0 (
    echo  [AVISO] Nenhum perfil encontrado neste nicho.
    pause
    goto menu_nicho
)

echo.
echo   0 - Voltar ao menu de nichos
echo.
echo  --------------------------------------------
set /p "esc_perfil=  Digite o(s) numero(s): "

if "!esc_perfil!"=="0" goto menu_nicho
if "!esc_perfil!"=="" goto menu_perfil

:: ================================================
::   MONTA LISTA DE PERFIS SELECIONADOS
:: ================================================
set "total_sel=0"

:: Substitui virgula por espaco para iterar
set "lista_nums=!esc_perfil:,= !"

for %%N in (!lista_nums!) do (
    set "n=%%N"
    :: Valida que e numero e esta no range
    if defined PERFIL_!n! (
        set /a total_sel+=1
        call set "SEL_!total_sel!=%%PERFIL_!n!%%"
    ) else (
        echo  [AVISO] Numero %%N invalido, ignorado.
    )
)

if !total_sel!==0 (
    echo  Nenhum perfil valido selecionado.
    timeout /t 2 /nobreak >nul
    goto menu_perfil
)

:: ================================================
::   MENU PROPORCAO
:: ================================================
:menu_proporcao
cls
echo.
echo  ============================================
echo    PROPORCAO
echo  ============================================
echo.
echo   Quais videos processar dentro de !PASTA_VIDEOS!?
echo.
echo   1 - 1:1   ^(subpasta 1por1^)
echo   2 - 4:5   ^(subpasta 4por5^)
echo   3 - 9:16  ^(subpasta 9por16^)
echo   4 - Todas ^(1:1 + 4:5 + 9:16 + soltos na raiz^)
echo.
echo  --------------------------------------------
set /p "esc_prop=  Digite o numero: "

set "PROP_SUBPASTA="
if "!esc_prop!"=="1" set "PROP_SUBPASTA=1por1"
if "!esc_prop!"=="2" set "PROP_SUBPASTA=4por5"
if "!esc_prop!"=="3" set "PROP_SUBPASTA=9por16"
if "!esc_prop!"=="4" set "PROP_SUBPASTA=TODAS"

if "!PROP_SUBPASTA!"=="" (
    echo  Opcao invalida.
    timeout /t 1 /nobreak >nul
    goto menu_proporcao
)

:: ================================================
::   CONFIRMACAO
:: ================================================
cls
echo.
echo  ============================================
echo    CONFIRMACAO
echo  ============================================
echo.
echo   Nicho     : !NICHO_SEL!
echo   Proporcao : !PROP_SUBPASTA!
echo.
for /l %%I in (1,1,!total_sel!) do (
    echo   %%I - !SEL_%%I!
    echo          !RAIZ!\!NICHO_SEL!\!SEL_%%I!\!PASTA_VIDEOS!
)
echo.
set /p "ok=  Confirma processamento? (S/N): "
if /i "!ok!"=="N" goto menu_perfil
if /i "!ok!" NEQ "S" goto menu_perfil

:: ================================================
::   PROCESSA CADA PERFIL SELECIONADO
:: ================================================
set "total_geral=0"
set "success_geral=0"
set "errors_geral=0"
set "inicio_geral=%time%"

for /l %%I in (1,1,!total_sel!) do (
    set "PERFIL_ATUAL=!SEL_%%I!"
    set "ENTRADA=!RAIZ!\!NICHO_SEL!\!PERFIL_ATUAL!\!PASTA_VIDEOS!"
    if not exist "!ENTRADA!" set "ENTRADA=!RAIZ!\!NICHO_SEL!\!PERFIL_ATUAL!"
    set "PRONTOS_BASE=!RAIZ!\!NICHO_SEL!\!PERFIL_ATUAL!\!PASTA_LIMPOS!"

    echo.
    echo  ============================================
    echo    [%%I/!total_sel!] !NICHO_SEL! \ !PERFIL_ATUAL!
    echo  ============================================
    echo.

    if /i "!PROP_SUBPASTA!"=="TODAS" (
        set "SCAN_ALVO=!ENTRADA!"
    ) else (
        set "SCAN_ALVO=!ENTRADA!\!PROP_SUBPASTA!"
    )

    if not exist "!SCAN_ALVO!" (
        echo  [AVISO] Pasta nao encontrada: !SCAN_ALVO!
        echo  Pulando...
        echo.
    ) else (

    echo  Entrada : !SCAN_ALVO!
    echo  Saida   : !PRONTOS_BASE!
    echo.

    :: Conta videos (inclui subpastas, ex: 1por1, 4por5, 9por16)
    set "total=0"
    for /f "usebackq delims=" %%F in (`dir /b /s /a-d "!SCAN_ALVO!\*.mp4" "!SCAN_ALVO!\*.mov" "!SCAN_ALVO!\*.avi" "!SCAN_ALVO!\*.mkv" "!SCAN_ALVO!\*.m4v" 2^>nul`) do set /a total+=1

    if !total!==0 (
        echo  [AVISO] Nenhum video encontrado. Pulando.
        echo.
    ) else (

    echo  !total! video^(s^) encontrado^(s^).
    echo.
    set /a total_geral+=!total!
    set "count=0"

    for /f "usebackq delims=" %%F in (`dir /b /s /a-d "!SCAN_ALVO!\*.mp4" "!SCAN_ALVO!\*.mov" "!SCAN_ALVO!\*.avi" "!SCAN_ALVO!\*.mkv" "!SCAN_ALVO!\*.m4v" 2^>nul`) do (
        set /a count+=1
        set "ARQUIVO_IN=%%F"
        set "NOME_BASE=%%~nF"
        set "logfile=!PRONTOS_BASE!\log_!count!.txt"

        echo  [!count!/!total!] %%~nxF

        :: Duracao
        set "dur_seg=5"
        for /f "tokens=1 delims=." %%D in ('ffprobe -v error -show_entries format^=duration -of default^=noprint_wrappers^=1^:nokey^=1 "!ARQUIVO_IN!" 2^>nul') do set "dur_seg=%%D"

        :: Resolucao original (so para exibir no log, nao e usada para redimensionar)
        set "VID_W=0"
        set "VID_H=0"
        for /f "tokens=1,2 delims=x" %%W in ('ffprobe -v error -select_streams v:0 -show_entries stream^=width^,height -of csv^=s^=x:p^=0 "!ARQUIVO_IN!" 2^>nul') do (
            set "VID_W=%%W"
            set "VID_H=%%X"
        )

        :: Pasta de origem do arquivo (herda o nome se estiver numa subpasta de proporcao)
        set "PASTA_ORIGEM="
        for %%P in ("!ARQUIVO_IN!\..") do set "PASTA_ORIGEM=%%~nxP"

        set "PASTA_PROP="
        if /i "!PASTA_ORIGEM!"=="1por1"  set "PASTA_PROP=1por1"
        if /i "!PASTA_ORIGEM!"=="4por5"  set "PASTA_PROP=4por5"
        if /i "!PASTA_ORIGEM!"=="9por16" set "PASTA_PROP=9por16"

        if "!PASTA_PROP!"=="" (
            :: Solto na raiz de VIDEOS RECORTADOS: classifica pela resolucao real, sem redimensionar
            set "PASTA_PROP=9por16"
            if !VID_W! GTR 0 if !VID_H! GTR 0 (
                set /a "RATIO100=!VID_W!*100/!VID_H!"
                if !RATIO100! GEQ 90 if !RATIO100! LEQ 110 set "PASTA_PROP=1por1"
                if !RATIO100! GEQ 75 if !RATIO100! LEQ 89  set "PASTA_PROP=4por5"
            )
        )

        if not exist "!PRONTOS_BASE!\!PASTA_PROP!" mkdir "!PRONTOS_BASE!\!PASTA_PROP!"
        set "outfile=!PRONTOS_BASE!\!PASTA_PROP!\!NOME_BASE!.mp4"

        echo         !dur_seg!s ^| !VID_W!x!VID_H! ^| -^> !PASTA_PROP! ^| velocidade !UNIC_SPEED!x

        :: Filtros video
        if "!UNIC_CROP_TOPO!"=="1" (set "VF=crop=iw:ih-1:0:1") else (set "VF=null")
        set "VF=!VF!,unsharp=5:5:1.6:5:5:0.0"
        set "VF=!VF!,eq=contrast=1.08:saturation=1.15:brightness=0.01:gamma=1.03"
        if not "!UNIC_HUE!"=="0"     set "VF=!VF!,hue=h=!UNIC_HUE!"
        if "!UNIC_LENS!"=="1"        set "VF=!VF!,lenscorrection=k1=0.01:k2=0.01"
        if not "!UNIC_NOISE!"=="0"   set "VF=!VF!,noise=alls=!UNIC_NOISE!:allf=t"
        if "!UNIC_DEFLICKER!"=="1"   set "VF=!VF!,deflicker=size=2:mode=am"
        if not "!UNIC_SPEED!"=="1.00" set "VF=!VF!,setpts=PTS/!UNIC_SPEED!"
        if not "!UNIC_FADE!"=="0" (
            set /a fout=!dur_seg!-1
            if !fout! LSS 1 set "fout=1"
            set "VF=!VF!,fade=t=in:st=0:d=!UNIC_FADE!,fade=t=out:st=!fout!:d=!UNIC_FADE!"
        )
        set "VF=!VF!,format=yuv420p"

        :: Blur nas faixas de cima/baixo (cobre @usuario mesmo com posicao variavel)
        set "FILTROGRAFO="
        set "MAPVIDEO=-vf "!VF!""
        if "!UNIC_BLUR_MARCA!"=="1" (
            set "FILTROGRAFO=[0:v]!VF!,split=3[vmain][vbot][vtop];[vbot]crop=iw:ih*!BLUR_FAIXA_BAIXO!:0:ih*(1-!BLUR_FAIXA_BAIXO!),gblur=sigma=!BLUR_FORCA!:steps=3[vblurbot];[vtop]crop=iw:ih*!BLUR_FAIXA_TOPO!:0:0,gblur=sigma=!BLUR_FORCA!:steps=3[vblurtop];[vmain][vblurbot]overlay=0:H-h[vtmp];[vtmp][vblurtop]overlay=0:0[vout]"
            set "MAPVIDEO=-filter_complex "!FILTROGRAFO!" -map "[vout]" -map 0:a?"
        )

        :: Filtros audio
        set "AF="
        if not "!UNIC_PITCH!"=="1.0" (
            if not "!UNIC_SPEED!"=="1.00" (
                set "AF=asetrate=44100*!UNIC_PITCH!,aresample=44100,atempo=!UNIC_SPEED!"
            ) else (
                set "AF=asetrate=44100*!UNIC_PITCH!,aresample=44100"
            )
        ) else (
            if not "!UNIC_SPEED!"=="1.00" set "AF=atempo=!UNIC_SPEED!"
        )
        if "!UNIC_EQ_AUDIO!"=="1" (
            if "!AF!"=="" (set "AF=equalizer=f=60:width_type=o:width=2:g=-1,equalizer=f=12000:width_type=o:width=2:g=-1"
            ) else (set "AF=!AF!,equalizer=f=60:width_type=o:width=2:g=-1,equalizer=f=12000:width_type=o:width=2:g=-1")
        )
        if not "!UNIC_FADE!"=="0" (
            set /a afout=!dur_seg!-1
            if !afout! LSS 1 set "afout=1"
            if "!AF!"=="" (set "AF=afade=t=in:st=0:d=!UNIC_FADE!,afade=t=out:st=!afout!:d=!UNIC_FADE!"
            ) else (set "AF=!AF!,afade=t=in:st=0:d=!UNIC_FADE!,afade=t=out:st=!afout!:d=!UNIC_FADE!")
        )

        set "TRIM="
        if not "!UNIC_TRIM_START!"=="0" set "TRIM=-ss !UNIC_TRIM_START!"
        set "AFFLAG="
        if not "!AF!"=="" set "AFFLAG=-af "!AF!""

        echo         Processando...
        ffmpeg -hide_banner -nostdin !TRIM! -i "!ARQUIVO_IN!" -map_metadata -1 -map_metadata:s:v -1 -map_metadata:s:a -1 -fflags +bitexact !MAPVIDEO! -r !FPS_SAIDA! -c:v !CODEC_VIDEO! -b:v !BITRATE_VIDEO! -preset !PRESET! -c:a aac -b:a !BITRATE_AUDIO! !AFFLAG! -f mov -brand qt -movflags +faststart -metadata make="!META_MAKE!" -metadata model="!META_MODEL!" -metadata creation_time="!META_CREATION!" -metadata:s:v handler_name="Core Media Video" -metadata:s:v encoder="" -metadata:s:a handler_name="Core Media Audio" -metadata:s:a encoder="" "!outfile!" -y >"!logfile!" 2>&1

        if exist "!outfile!" (
            for %%S in ("!outfile!") do set "fsz=%%~zS"
            if !fsz! GTR 0 (
                set /a success_geral+=1
                echo         [OK] -^> !PASTA_PROP!\!NOME_BASE!.mp4
                del "!logfile!" >nul 2>&1
            ) else (
                set /a errors_geral+=1
                del "!outfile!" >nul 2>&1
                echo         [ERRO] Saida vazia.
            )
        ) else (
            set /a errors_geral+=1
            echo         [ERRO] Falha ffmpeg. Log: !logfile!
        )
        echo.
    )
    )
    )

    echo  --------------------------------------------
    echo.
)

:: ================================================
::   RESUMO GERAL
:: ================================================
echo.
echo  ============================================
echo    RESUMO GERAL
echo    Perfis    : !total_sel!
echo    Videos    : !total_geral!
echo    OK        : !success_geral!
echo    Erros     : !errors_geral!
echo    Inicio    : !inicio_geral!
echo    Fim       : %time%
echo  ============================================
echo.
pause
goto menu_nicho
