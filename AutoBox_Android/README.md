# AutoBoxV Coleta — Android 0.1.0 (teste)

Versão experimental para Android 8.0 ou superior, com Android System WebView atualizado. Foi preparada para testar no Infinix HOT do usuário; o modelo exato e a versão do Android ainda não foram informados. Não foi testada em aparelho físico nem no jogo autenticado.

## O que faz

- Abre o site oficial e o jogo dentro do aplicativo. O usuário faz login normalmente no próprio site.
- Iniciar, Pausar e Parar; seleção de coleta pela nave ou somente pelo PET.
- Coleta apenas boxes comuns/bônus. Não abre caixas verdes, compra itens, ataca NPCs ou jogadores, repara ou renasce automaticamente.
- Mantém a tela acesa durante a coleta. Ao sair do aplicativo ou bloquear a tela, a coleta pausa e exige Iniciar novamente.
- Interrompe em combate, salto, morte, vida de 25% ou menos, mudança de conta/mapa/vida/configuração e leitura sem avanço do relógio do jogo por seis segundos.
- Usa os adaptadores de coleta já presentes no projeto de computador. A confirmação na coleta pela nave exige desaparecimento da box, avanço do contador do cliente e aproximação observada.

## Instalar e testar

1. Baixe o APK da versão de teste `android-0.1.0` no GitHub.
2. Autorize a instalação desse APK pelo navegador/gerenciador escolhido, quando o Android solicitar.
3. Abra AutoBoxV Coleta, faça login e entre no mapa.
4. Escolha Pela nave ou Somente PET. Para PET, equipe Auto-looter nível 1, PET nível 2+, com vida e combustível.
5. Toque em Iniciar e acompanhe alguns minutos com o aplicativo aberto. Use Pausar antes de trocar de aplicativo.

O APK é de desenvolvimento, assinado para instalação de teste. Não contém atualizador Android. A assinatura de desenvolvimento pode variar em uma futura compilação; nesse caso, uma instalação de teste anterior precisará ser removida antes de instalar outra, perdendo a sessão local.

## Privacidade e permissões

A única permissão do manifesto é INTERNET. Não solicita acessibilidade, controle remoto, contatos, arquivos ou root. A sessão do site fica no armazenamento do WebView do aparelho. Não há ponte JavaScript de login nem envio de credenciais para outro servidor. A navegação principal aceita apenas HTTPS no domínio interstellar-verse.com; erros de certificado não são ignorados.

## Compilar e verificar

Requer JDK 17, Gradle 8.9 e Android SDK com plataforma 35/build-tools 34.0.0:

```sh
node AutoBox_Android/tests/collector.test.mjs
cd AutoBox_Android
gradle :app:assembleDebug :app:lintDebug
```

O workflow dedicado testa o controlador, compila o APK, executa lint, verifica a assinatura e publica uma prévia Android. Ele não modifica o executável nem o manifesto de atualização do Windows.

## Limitações da primeira versão

- O funcionamento do login e da coleta dentro do WebView ainda precisa ser validado no Infinix HOT. Se o site usar um cliente diferente no celular, o controlador pausa informando a integração indisponível.
- Não promete coleta com tela apagada ou uso em segundo plano.
- Não registra vídeo, dados de login ou o tráfego de autenticação. Falhas de adaptação precisam ser relatadas pelo status mostrado no aplicativo.
