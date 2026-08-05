Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$outputFile = $args[0]
$raiz = "D:\fnkSocialMidia\fnkPerfis"

if (-not (Test-Path $raiz)) {
    [System.Windows.Forms.MessageBox]::Show("Pasta raiz nao encontrada:`n$raiz", "Erro")
    exit
}

# Busca todas as pastas VIDEOS RECORTADOS em toda a arvore Nicho\Perfil\VIDEOS RECORTADOS
$pastaAlvo = "VIDEOS RECORTADOS"
$todasPastas = @()

foreach ($nicho in Get-ChildItem -Path $raiz -Directory) {
    foreach ($perfil in Get-ChildItem -Path $nicho.FullName -Directory) {
        $candidato = Join-Path $perfil.FullName $pastaAlvo
        if (Test-Path $candidato) {
            $todasPastas += [PSCustomObject]@{
                Display = "$($nicho.Name)  \  $($perfil.Name)  \  $pastaAlvo"
                FullPath = $candidato
            }
        }
    }
}

if ($todasPastas.Count -eq 0) {
    [System.Windows.Forms.MessageBox]::Show("Nenhuma pasta '$pastaAlvo' encontrada dentro de:`n$raiz", "Aviso")
    exit
}

# ---- Janela ----
$form = New-Object System.Windows.Forms.Form
$form.Text = "Selecione as pastas para processar  (Ctrl+Clique = multiplas | Shift+Clique = intervalo)"
$form.Size = New-Object System.Drawing.Size(860, 580)
$form.StartPosition = "CenterScreen"
$form.TopMost = $true
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$label = New-Object System.Windows.Forms.Label
$label.Text = "Raiz: $raiz    |    Buscando: \Nicho\Perfil\$pastaAlvo"
$label.Location = New-Object System.Drawing.Point(10, 8)
$label.Size = New-Object System.Drawing.Size(830, 18)
$label.Font = New-Object System.Drawing.Font("Consolas", 8)
$form.Controls.Add($label)

$list = New-Object System.Windows.Forms.ListBox
$list.Location = New-Object System.Drawing.Point(10, 30)
$list.Size = New-Object System.Drawing.Size(830, 450)
$list.SelectionMode = "MultiExtended"
$list.Font = New-Object System.Drawing.Font("Consolas", 10)
$list.HorizontalScrollbar = $true
foreach ($p in $todasPastas) { [void]$list.Items.Add($p.Display) }
$form.Controls.Add($list)

$btnOk = New-Object System.Windows.Forms.Button
$btnOk.Text = "PROCESSAR SELECIONADAS"
$btnOk.Location = New-Object System.Drawing.Point(10, 492)
$btnOk.Size = New-Object System.Drawing.Size(220, 35)
$btnOk.BackColor = [System.Drawing.Color]::FromArgb(0, 120, 212)
$btnOk.ForeColor = [System.Drawing.Color]::White
$btnOk.FlatStyle = "Flat"
$btnOk.Font = New-Object System.Drawing.Font("Consolas", 9, [System.Drawing.FontStyle]::Bold)
$btnOk.Add_Click({
    if ($list.SelectedIndices.Count -eq 0) {
        [System.Windows.Forms.MessageBox]::Show("Selecione ao menos uma pasta.", "Aviso")
        return
    }
    $sw = New-Object System.IO.StreamWriter($outputFile, $false, [System.Text.Encoding]::ASCII)
    foreach ($i in $list.SelectedIndices) {
        $sw.WriteLine($todasPastas[$i].FullPath)
    }
    $sw.Close()
    $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Close()
})
$form.Controls.Add($btnOk)

$btnTodas = New-Object System.Windows.Forms.Button
$btnTodas.Text = "SELECIONAR TODAS"
$btnTodas.Location = New-Object System.Drawing.Point(240, 492)
$btnTodas.Size = New-Object System.Drawing.Size(180, 35)
$btnTodas.Font = New-Object System.Drawing.Font("Consolas", 9)
$btnTodas.Add_Click({ for ($i = 0; $i -lt $list.Items.Count; $i++) { $list.SetSelected($i, $true) } })
$form.Controls.Add($btnTodas)

$btnCancelar = New-Object System.Windows.Forms.Button
$btnCancelar.Text = "CANCELAR"
$btnCancelar.Location = New-Object System.Drawing.Point(430, 492)
$btnCancelar.Size = New-Object System.Drawing.Size(120, 35)
$btnCancelar.Font = New-Object System.Drawing.Font("Consolas", 9)
$btnCancelar.Add_Click({
    $form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.Close()
})
$form.Controls.Add($btnCancelar)

$form.ShowDialog() | Out-Null
