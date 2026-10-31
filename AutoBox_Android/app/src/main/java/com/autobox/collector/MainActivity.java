package com.autobox.collector;

import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;
import org.json.JSONTokener;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/** Collection only. The game owns authentication; no password or token bridge exists. */
public final class MainActivity extends Activity {
    private static final String HOME = "https://interstellar-verse.com/";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private WebView web;
    private TextView status, stats;
    private Button start;
    private Spinner mode;
    private boolean running = false, inFlight = false, foreground = false;
    private int generation = 0;
    private String controller;

    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!running || !foreground || inFlight) return;
            if (!isGame(web.getUrl())) { pause("Entre no mapa do jogo para coletar."); return; }
            final int token = generation;
            inFlight = true;
            web.evaluateJavascript("JSON.stringify(window.AutoBoxAndroid?.tick() || {running:false,status:'Reabra o mapa e inicie novamente.'})", value -> {
                if (token != generation || !foreground) return;
                inFlight = false;
                if (update(value) && running) handler.postDelayed(this, 450);
            });
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(28,32,35));
        getWindow().setNavigationBarColor(Color.rgb(28,32,35));
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(28,32,35));
        LinearLayout bar = new LinearLayout(this);
        bar.setPadding(dp(8),dp(2),dp(8),dp(2));
        bar.setGravity(android.view.Gravity.CENTER_VERTICAL);
        TextView title = label("AutoBoxV Coleta\n0.1.0 · TESTE", 13);
        bar.addView(title, new LinearLayout.LayoutParams(0,-2,1));
        mode = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item,
                new String[]{"Pela nave", "Somente PET"});
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        mode.setAdapter(adapter);
        bar.addView(mode, new LinearLayout.LayoutParams(dp(145),-2));
        start = button("Iniciar", this::startCollection);
        bar.addView(start);
        bar.addView(button("Pausar", () -> pause("Coleta pausada.")));
        bar.addView(button("Parar", () -> pause("Coleta encerrada.")));
        bar.addView(button("Login / início", () -> { pause("Entre no jogo pela página inicial."); web.loadUrl(HOME); }));
        root.addView(bar);
        stats = label("Somente coleta · Sem NPC Killer · Mantenha o aplicativo aberto", 12);
        stats.setPadding(dp(10),0,dp(10),dp(3));
        root.addView(stats);
        web = new WebView(this);
        root.addView(web,new LinearLayout.LayoutParams(-1,0,1));
        status = label("Faça login e entre no mapa; depois toque em Iniciar.", 12);
        status.setPadding(dp(10),dp(3),dp(10),dp(4));
        root.addView(status);
        root.setOnApplyWindowInsetsListener((view,insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(root);
        root.requestApplyInsets();

        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSafeBrowsingEnabled(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (allowed(request.getUrl())) return false;
                Toast.makeText(MainActivity.this,"Link externo bloqueado neste aplicativo de coleta.",Toast.LENGTH_SHORT).show();
                return true;
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                pause("Página carregando. Inicie a coleta após entrar no mapa.");
                if (!allowed(Uri.parse(url))) view.stopLoading();
            }
            @Override public void onPageFinished(WebView view,String url) {
                CookieManager.getInstance().flush();
                status.setText(isGame(url) ? "Entre no mapa e toque em Iniciar. Coleta apenas com o app aberto." : "Faça login e abra o mapa do jogo.");
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error) {
                if (request.isForMainFrame()) pause("Página indisponível. Confira a conexão e abra o jogo novamente.");
            }
        });
        try {
            controller = "window.AutoBoxAndroidTarget="+asset("collect-target.js")+";\n"
                       + "window.AutoBoxAndroidPet="+asset("pet-collect.js")+";\n"+asset("collector.js");
        } catch (Exception e) {
            status.setText("Não foi possível carregar o controlador. Reinstale o APK de teste.");
            start.setEnabled(false);
        }
        web.loadUrl(HOME);
    }

    private static boolean allowed(Uri uri) {
        return "https".equals(uri.getScheme()) && "interstellar-verse.com".equals(uri.getHost())
                && (uri.getPort() == -1 || uri.getPort() == 443) && uri.getUserInfo() == null;
    }
    private static boolean isGame(String url) {
        if (url == null) return false;
        Uri uri = Uri.parse(url);
        return allowed(uri) && ("/play/".equals(uri.getPath()) || "/play".equals(uri.getPath()));
    }
    private void startCollection() {
        if (!foreground || running || controller == null) return;
        if (!isGame(web.getUrl())) { status.setText("Faça login e entre no mapa primeiro."); return; }
        generation++; final int token = generation;
        running = true; inFlight = true; mode.setEnabled(false); start.setEnabled(false);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        String selected = mode.getSelectedItemPosition() == 1 ? "pet" : "ship";
        String script = controller+"\nJSON.stringify(window.AutoBoxAndroid.start("+JSONObject.quote(selected)+"));";
        web.evaluateJavascript(script,value -> {
            if (token != generation || !foreground) return;
            inFlight = false;
            if (update(value) && running) handler.postDelayed(poll,450);
        });
    }
    private boolean update(String value) {
        try {
            Object result = new JSONTokener(value).nextValue();
            JSONObject data = result instanceof String ? new JSONObject((String)result) : (JSONObject)result;
            status.setText(data.optString("status","Aguardando dados."));
            if (data.has("hp")) stats.setText("Mapa "+data.optString("map","—")+" · HP "+data.optInt("hp")+"% · Boxes "+data.optInt("boxes")
                    +(mode.getSelectedItemPosition()==1 ? " · Coleta pelo PET" : " · Confirmadas "+data.optInt("confirmed"))+" · Uridium "+(data.isNull("uridium") ? "—" : data.optString("uridium")));
            if (!data.optBoolean("running",false)) {
                pause(data.optString("status","Coleta pausada.")); return false;
            }
            return true;
        } catch (Exception e) { pause("Resposta do jogo indisponível. Inicie novamente após entrar no mapa."); return false; }
    }
    private void pause(String message) {
        generation++; running = false; inFlight = false; handler.removeCallbacks(poll);
        if (start != null) start.setEnabled(controller != null);
        if (mode != null) mode.setEnabled(true);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (web != null && isGame(web.getUrl())) web.evaluateJavascript("window.AutoBoxAndroid?.stop();",null);
        if (status != null) status.setText(message);
    }
    private String asset(String name) throws Exception {
        try (InputStream input = getAssets().open(name); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096]; int count;
            while ((count=input.read(buffer)) != -1) out.write(buffer,0,count);
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }
    private int dp(int n) { return Math.round(n*getResources().getDisplayMetrics().density); }
    private TextView label(String text,int size) {
        TextView view=new TextView(this);view.setText(text);view.setTextSize(size);view.setTextColor(Color.rgb(220,231,225));return view;
    }
    private Button button(String text,Runnable command) {
        Button button=new Button(this);button.setText(text);button.setTextSize(11);button.setMinWidth(0);button.setMinimumWidth(0);
        button.setPadding(dp(8),0,dp(8),0);button.setOnClickListener(v -> command.run());return button;
    }
    @Override protected void onResume() { super.onResume();foreground=true;if (web != null) web.onResume(); }
    @Override protected void onPause() {
        foreground=false;pause("Coleta pausada ao sair do app. Toque em Iniciar para retomar.");
        if (web != null) { CookieManager.getInstance().flush();web.onPause(); }
        super.onPause();
    }
    @Override public void onBackPressed() {
        pause("Coleta pausada.");
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
    @Override protected void onDestroy() {
        pause("Aplicativo encerrado.");
        if (web != null) { web.stopLoading();web.destroy();web=null; }
        super.onDestroy();
    }
}
