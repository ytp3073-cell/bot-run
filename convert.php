<?php
header("Content-Type: application/json; charset=utf-8");

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error'=>'POST required']); exit;
}
if (!isset($_FILES['audio'])) {
    http_response_code(400);
    echo json_encode(['error'=>'audio file required']); exit;
}

// ensure folders exist
@mkdir('uploads',0755,true);
@mkdir('outputs',0755,true);

// save upload
$tmp = $_FILES['audio']['tmp_name'];
$name = basename($_FILES['audio']['name']);
$inPath = 'uploads/'.time().'_'.preg_replace('/[^a-zA-Z0-9._-]/','_',$name);
move_uploaded_file($tmp, $inPath);

// params
$semitones = isset($_POST['semitones']) ? floatval($_POST['semitones']) : 5.0;
$format    = isset($_POST['format']) ? strtolower($_POST['format']) : 'wav';

// compute filter
$ratio = pow(2, $semitones/12);
$sr = 44100;
$filter = "asetrate={$sr}*{$ratio},aresample={$sr},atempo=".(1/$ratio);

$outName = 'out_'.time().'.'.$format;
$outPath = 'outputs/'.$outName;

$cmd = "ffmpeg -y -i ".escapeshellarg($inPath)." -af ".escapeshellarg($filter)." -vn ".escapeshellarg($outPath)." 2>&1";
exec($cmd, $log, $rc);

if ($rc !== 0 || !file_exists($outPath)) {
    http_response_code(500);
    echo json_encode(['error'=>'ffmpeg failed','log'=>$log]); exit;
}

$base = (isset($_SERVER['HTTPS'])?'https':'http').'://'.$_SERVER['HTTP_HOST'].rtrim(dirname($_SERVER['REQUEST_URI']),'/');
echo json_encode(['ok'=>true,'file'=>$base.'/'.$outPath]);