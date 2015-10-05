# Add and populate a blacklist of disposable email address providers, so we can prevent them
# from signing up with us.
CREATE TABLE `email_domain_blacklist` (
  `domain` varchar(255) NOT NULL,
  UNIQUE KEY `domain_index` (`domain`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
INSERT INTO `email_domain_blacklist` VALUES ('0-mail.com'),('0815.ru'),('0815.su'),('0clickemail.com'),('0wnd.net'),('0wnd.org'),('10minutemail.co.za'),('10minutemail.com'),('10minutemail.de'),('123-m.com'),('1chuan.com'),('1fsdfdsfsdf.tk'),('1pad.de'),('1zhuan.com'),('20mail.it'),('20minutemail.com'),('21cn.com'),('2fdgdfgdfgdf.tk'),('2prong.com'),('30minutemail.com'),('33mail.com'),('3d-painting.com'),('3trtretgfrfe.tk'),('4gfdsgfdgfd.tk'),('4warding.com'),('4warding.net'),('4warding.org'),('5ghgfhfghfgh.tk'),('60minutemail.com'),('675hosting.com'),('675hosting.net'),('675hosting.org'),('6hjgjhgkilkj.tk'),('6ip.us'),('6paq.com'),('6url.com'),('75hosting.com'),('75hosting.net'),('75hosting.org'),('7days-printing.com'),('7tags.com'),('99experts.com'),('9ox.net'),('a-bc.net'),('a45.in'),('abcmail.email'),('acentri.com'),('advantimo.com'),('afrobacon.com'),('ag.us.to'),('agedmail.com'),('ahk.jp'),('ajaxapp.net'),('alivance.com'),('ama-trade.de'),('amail.com'),('amilegit.com'),('amiri.net'),('amiriindustries.com'),('anappthat.com'),('ano-mail.net'),('anonbox.net'),('anonmails.de'),('anonymail.dk'),('anonymbox.com'),('antichef.com'),('antichef.net'),('antireg.ru'),('antispam.de'),('antispammail.de'),('appixie.com'),('armyspy.com'),('artman-conception.com'),('aver.com'),('azmeil.tk'),('baxomale.ht.cx'),('beddly.com'),('beefmilk.com'),('bigprofessor.so'),('bigstring.com'),('binkmail.com'),('bio-muesli.net'),('blogmyway.org'),('bobmail.info'),('bodhi.lawlita.com'),('bofthew.com'),('bootybay.de'),('boun.cr'),('bouncr.com'),('boxformail.in'),('breakthru.com'),('brefmail.com'),('brennendesreich.de'),('broadbandninja.com'),('bsnow.net'),('bspamfree.org'),('bu.mintemail.com'),('buffemail.com'),('bugmenot.com'),('bumpymail.com'),('bund.us'),('bundes-li.ga'),('burnthespam.info'),('burstmail.info'),('buymoreplays.com'),('buyusedlibrarybooks.org'),('byom.de'),('c2.hu'),('cachedot.net'),('card.zp.ua'),('casualdx.com'),('cbair.com'),('cek.pm'),('cellurl.com'),('centermail.com'),('centermail.net'),('chammy.info'),('cheatmail.de'),('childsavetrust.org'),('chogmail.com'),('choicemail1.com'),('chong-mail.com'),('chong-mail.net'),('chong-mail.org'),('clixser.com'),('cmail.com'),('cmail.net'),('cmail.org'),('coldemail.info'),('consumerriot.com'),('cool.fr.nf'),('correo.blogos.net'),('cosmorph.com'),('courriel.fr.nf'),('courrieltemporaire.com'),('crapmail.org'),('crazymailing.com'),('cubiclink.com'),('curryworld.de'),('cust.in'),('cuvox.de'),('d3p.dk'),('dacoolest.com'),('daintly.com'),('dandikmail.com'),('dayrep.com'),('dbunker.com'),('dcemail.com'),('deadaddress.com'),('deadspam.com'),('deagot.com'),('dealja.com'),('delikkt.de'),('despam.it'),('despammed.com'),('devnullmail.com'),('dfgh.net'),('digitalsanctuary.com'),('dingbone.com'),('discard.email'),('discardmail.com'),('discardmail.de'),('disposableaddress.com'),('disposableemailaddresses.com'),('disposableemailaddresses.emailmiser.com'),('disposableinbox.com'),('dispose.it'),('disposeamail.com'),('disposemail.com'),('dispostable.com'),('dm.w3internet.co.uk'),('dm.w3internet.co.ukexample.com'),('dodgeit.com'),('dodgit.com'),('dodgit.org'),('doiea.com'),('domozmail.com'),('donemail.ru'),('dontreg.com'),('dontsendmespam.de'),('dotmsg.com'),('drdrb.com'),('drdrb.net'),('droplar.com'),('duam.net'),('dudmail.com'),('dump-email.info'),('dumpandjunk.com'),('dumpmail.de'),('dumpyemail.com'),('duskmail.com'),('e-mail.com'),('e-mail.org'),('e4ward.com'),('easytrashmail.com'),('einmalmail.de'),('einrot.com'),('einrot.de'),('eintagsmail.de'),('email60.com'),('emaildienst.de'),('emailgo.de'),('emailias.com'),('emailigo.de'),('emailinfive.com'),('emaillime.com'),('emailmiser.com'),('emailproxsy.com'),('emailsensei.com'),('emailtemporanea.com'),('emailtemporanea.net'),('emailtemporar.ro'),('emailtemporario.com.br'),('emailthe.net'),('emailtmp.com'),('emailto.de'),('emailwarden.com'),('emailx.at.hm'),('emailxfer.com'),('emeil.in'),('emeil.ir'),('emil.com'),('emz.net'),('enterto.com'),('ephemail.net'),('ero-tube.org'),('etranquil.com'),('etranquil.net'),('etranquil.org'),('evopo.com'),('explodemail.com'),('express.net.ua'),('eyepaste.com'),('fakeinbox.com'),('fakeinformation.com'),('fakemail.fr'),('fakemailz.com'),('fammix.com'),('fansworldwide.de'),('fantasymail.de'),('fastacura.com'),('fastchevy.com'),('fastchrysler.com'),('fastkawasaki.com'),('fastmazda.com'),('fastmitsubishi.com'),('fastnissan.com'),('fastsubaru.com'),('fastsuzuki.com'),('fasttoyota.com'),('fastyamaha.com'),('fatflap.com'),('fdfdsfds.com'),('fightallspam.com'),('fiifke.de'),('filzmail.com'),('fivemail.de'),('fixmail.tk'),('fizmail.com'),('fleckens.hu'),('flyspam.com'),('footard.com'),('forgetmail.com'),('fr33mail.info'),('frapmail.com'),('freundin.ru'),('friendlymail.co.uk'),('front14.org'),('fuckingduh.com'),('fudgerub.com'),('fux0ringduh.com'),('fyii.de'),('garliclife.com'),('gehensiemirnichtaufdensack.de'),('gelitik.in'),('get1mail.com'),('get2mail.fr'),('getairmail.com'),('getmails.eu'),('getonemail.com'),('getonemail.net'),('ghosttexter.de'),('giantmail.de'),('girlsundertheinfluence.com'),('gishpuppy.com'),('gmial.com'),('goemailgo.com'),('gorillaswithdirtyarmpits.com'),('gotmail.com'),('gotmail.net'),('gotmail.org'),('gotti.otherinbox.com'),('gowikibooks.com'),('gowikicampus.com'),('gowikicars.com'),('gowikifilms.com'),('gowikigames.com'),('gowikimusic.com'),('gowikinetwork.com'),('gowikitravel.com'),('gowikitv.com'),('grandmamail.com'),('grandmasmail.com'),('great-host.in'),('greensloth.com'),('grr.la'),('gsrv.co.uk'),('guerillamail.biz'),('guerillamail.com'),('guerillamail.net'),('guerillamail.org'),('guerrillamail.biz'),('guerrillamail.com'),('guerrillamail.de'),('guerrillamail.info'),('guerrillamail.net'),('guerrillamail.org'),('guerrillamailblock.com'),('gustr.com'),('h.mintemail.com'),('h8s.org'),('hacccc.com'),('haltospam.com'),('harakirimail.com'),('hartbot.de'),('hat-geld.de'),('hatespam.org'),('hellodream.mobi'),('herp.in'),('hidemail.de'),('hidzz.com'),('hmamail.com'),('hochsitze.com'),('hopemail.biz'),('hotpop.com'),('hulapla.de'),('ieatspam.eu'),('ieatspam.info'),('ieh-mail.de'),('ihateyoualot.info'),('iheartspam.org'),('ikbenspamvrij.nl'),('imails.info'),('imgof.com'),('imstations.com'),('inbax.tk'),('inbox.si'),('inboxalias.com'),('inboxclean.com'),('inboxclean.org'),('inboxproxy.com'),('incognitomail.com'),('incognitomail.net'),('incognitomail.org'),('infocom.zp.ua'),('inoutmail.de'),('inoutmail.eu'),('inoutmail.info'),('inoutmail.net'),('insorg-mail.info'),('instant-mail.de'),('ip6.li'),('ipoo.org'),('irish2me.com'),('iwi.net'),('jetable.com'),('jetable.fr.nf'),('jetable.net'),('jetable.org'),('jnxjn.com'),('jourrapide.com'),('jsrsolutions.com'),('junk1e.com'),('kasmail.com'),('kaspop.com'),('keepmymail.com'),('killmail.com'),('killmail.net'),('kimsdisk.com'),('kingsq.ga'),('kir.ch.tc'),('klassmaster.com'),('klassmaster.net'),('klzlk.com'),('kook.ml'),('koszmail.pl'),('kulturbetrieb.info'),('kurzepost.de'),('l33r.eu'),('lackmail.net'),('lags.us'),('lawlita.com'),('lazyinbox.com'),('letthemeatspam.com'),('lhsdv.com'),('lifebyfood.com'),('link2mail.net'),('litedrop.com'),('loadby.us'),('login-email.ml'),('lol.ovpn.to'),('lolfreak.net'),('lookugly.com'),('lopl.co.cc'),('lortemail.dk'),('lovemeleaveme.com'),('lr78.com'),('lroid.com'),('lukop.dk'),('m21.cc'),('m4ilweb.info'),('maboard.com'),('mail-filter.com'),('mail-temporaire.fr'),('mail.by'),('mail.mezimages.net'),('mail.zp.ua'),('mail114.net'),('mail1a.de'),('mail21.cc'),('mail2rss.org'),('mail333.com'),('mail4trash.com'),('mailbidon.com'),('mailbiz.biz'),('mailblocks.com'),('mailbucket.org'),('mailcat.biz'),('mailcatch.com'),('mailde.de'),('mailde.info'),('maildrop.cc'),('maildx.com'),('maileater.com'),('maileimer.de'),('mailexpire.com'),('mailfa.tk'),('mailforspam.com'),('mailfreeonline.com'),('mailfs.com'),('mailguard.me'),('mailimate.com'),('mailin8r.com'),('mailinater.com'),('mailinator.com'),('mailinator.net'),('mailinator.org'),('mailinator.us'),('mailinator2.com'),('mailincubator.com'),('mailismagic.com'),('mailmate.com'),('mailme.ir'),('mailme.lv'),('mailme24.com'),('mailmetrash.com'),('mailmoat.com'),('mailms.com'),('mailnator.com'),('mailnesia.com'),('mailnull.com'),('mailorg.org'),('mailpick.biz'),('mailproxsy.com'),('mailquack.com'),('mailrock.biz'),('mailscrap.com'),('mailshell.com'),('mailsiphon.com'),('mailslapping.com'),('mailslite.com'),('mailtemp.info'),('mailtome.de'),('mailtothis.com'),('mailtrash.net'),('mailtv.net'),('mailtv.tv'),('mailzilla.com'),('mailzilla.org'),('mailzilla.orgmbx.cc'),('makemetheking.com'),('manifestgenerator.com'),('manybrain.com'),('mbx.cc'),('mega.zik.dj'),('meinspamschutz.de'),('meltmail.com'),('messagebeamer.de'),('mezimages.net'),('mierdamail.com'),('migumail.com'),('ministry-of-silly-walks.de'),('mintemail.com'),('misterpinball.de'),('mjukglass.nu'),('moakt.com'),('mobi.web.id'),('mobileninja.co.uk'),('moburl.com'),('moncourrier.fr.nf'),('monemail.fr.nf'),('monmail.fr.nf'),('monumentmail.com'),('msa.minsmail.com'),('mt2009.com'),('mt2014.com'),('mx0.wwwnew.eu'),('my10minutemail.com'),('mycard.net.ua'),('mycleaninbox.net'),('myemailboxy.com'),('mymail-in.net'),('mymailoasis.com'),('mynetstore.de'),('mypacks.net'),('mypartyclip.de'),('myphantomemail.com'),('mysamp.de'),('myspaceinc.com'),('myspaceinc.net'),('myspaceinc.org'),('myspacepimpedup.com'),('myspamless.com'),('mytemp.email'),('mytempemail.com'),('mytempmail.com'),('mytrashmail.com'),('nabuma.com'),('neomailbox.com'),('nepwk.com'),('nervmich.net'),('nervtmich.net'),('netmails.com'),('netmails.net'),('netzidiot.de'),('neverbox.com'),('nice-4u.com'),('nincsmail.hu'),('nnh.com'),('no-spam.ws'),('noblepioneer.com'),('nobulk.com'),('noclickemail.com'),('nogmailspam.info'),('nomail.pw'),('nomail.xl.cx'),('nomail2me.com'),('nomorespamemails.com'),('nonspam.eu'),('nonspammer.de'),('noref.in'),('nospam.ze.tc'),('nospam4.us'),('nospamfor.us'),('nospammail.net'),('nospamthanks.info'),('notmailinator.com'),('notsharingmy.info'),('nowhere.org'),('nowmymail.com'),('nurfuerspam.de'),('nus.edu.sg'),('nwldx.com'),('objectmail.com'),('obobbo.com'),('odaymail.com'),('odnorazovoe.ru'),('one-time.email'),('oneoffemail.com'),('oneoffmail.com'),('onewaymail.com'),('onlatedotcom.info'),('online.ms'),('oopi.org'),('opayq.com'),('ordinaryamerican.net'),('otherinbox.com'),('ourklips.com'),('outlawspam.com'),('ovpn.to'),('owlpic.com'),('pancakemail.com'),('paplease.com'),('pcusers.otherinbox.com'),('pepbot.com'),('pfui.ru'),('pimpedupmyspace.com'),('pjjkp.com'),('plexolan.de'),('poczta.onet.pl'),('politikerclub.de'),('poofy.org'),('pookmail.com'),('privacy.net'),('privatdemail.net'),('privy-mail.com'),('privymail.de'),('proxymail.eu'),('prtnx.com'),('prtz.eu'),('punkass.com'),('putthisinyourspamdatabase.com'),('pwrby.com'),('quickinbox.com'),('quickmail.nl'),('rcpt.at'),('reallymymail.com'),('realtyalerts.ca'),('recode.me'),('recursor.net'),('recyclemail.dk'),('regbypass.com'),('regbypass.comsafe-mail.net'),('rejectmail.com'),('reliable-mail.com'),('rhyta.com'),('rklips.com'),('rmqkr.net'),('royal.net'),('rppkn.com'),('rtrtr.com'),('s0ny.net'),('safe-mail.net'),('safersignup.de'),('safetymail.info'),('safetypost.de'),('sandelf.de'),('saynotospams.com'),('schafmail.de'),('schrott-email.de'),('secretemail.de'),('secure-mail.biz'),('selfdestructingmail.com'),('selfdestructingmail.org'),('sendspamhere.com'),('senseless-entertainment.com'),('services391.com'),('sharedmailbox.org'),('sharklasers.com'),('shieldedmail.com'),('shieldemail.com'),('shiftmail.com'),('shitmail.me'),('shitmail.org'),('shitware.nl'),('shmeriously.com'),('shortmail.net'),('showslow.de'),('sibmail.com'),('sinnlos-mail.de'),('siteposter.net'),('skeefmail.com'),('slapsfromlastnight.com'),('slaskpost.se'),('slopsbox.com'),('slushmail.com'),('smashmail.de'),('smellfear.com'),('smellrear.com'),('snakemail.com'),('sneakemail.com'),('sneakmail.de'),('snkmail.com'),('sofimail.com'),('sofort-mail.de'),('softpls.asia'),('sogetthis.com'),('sohu.com'),('solvemail.info'),('soodonims.com'),('spam.la'),('spam.su'),('spam4.me'),('spamail.de'),('spamarrest.com'),('spamavert.com'),('spambob.com'),('spambob.net'),('spambob.org'),('spambog.com'),('spambog.de'),('spambog.net'),('spambog.ru'),('spambox.info'),('spambox.irishspringrealty.com'),('spambox.us'),('spamcannon.com'),('spamcannon.net'),('spamcero.com'),('spamcon.org'),('spamcorptastic.com'),('spamcowboy.com'),('spamcowboy.net'),('spamcowboy.org'),('spamday.com'),('spamex.com'),('spamfree.eu'),('spamfree24.com'),('spamfree24.de'),('spamfree24.eu'),('spamfree24.info'),('spamfree24.net'),('spamfree24.org'),('spamgoes.in'),('spamgourmet.com'),('spamgourmet.net'),('spamgourmet.org'),('spamherelots.com'),('spamhereplease.com'),('spamhole.com'),('spamify.com'),('spaminator.de'),('spamkill.info'),('spaml.com'),('spaml.de'),('spammotel.com'),('spamobox.com'),('spamoff.de'),('spamsalad.in'),('spamslicer.com'),('spamspot.com'),('spamstack.net'),('spamthis.co.uk'),('spamthisplease.com'),('spamtrail.com'),('spamtroll.net'),('speed.1s.fr'),('spikio.com'),('spoofmail.de'),('squizzy.de'),('ssoia.com'),('startkeys.com'),('stinkefinger.net'),('stop-my-spam.com'),('stuffmail.de'),('super-auswahl.de'),('supergreatmail.com'),('supermailer.jp'),('superrito.com'),('superstachel.de'),('suremail.info'),('svk.jp'),('sweetxxx.de'),('tagyourself.com'),('talkinator.com'),('tapchicuoihoi.com'),('teewars.org'),('teleworm.com'),('teleworm.us'),('temp-mail.org'),('temp-mail.ru'),('temp.emeraldwebmail.com'),('temp.headstrong.de'),('tempalias.com'),('tempe-mail.com'),('tempemail.biz'),('tempemail.co.za'),('tempemail.com'),('tempemail.net'),('tempinbox.co.uk'),('tempinbox.com'),('tempmail.eu'),('tempmail.it'),('tempmail2.com'),('tempmaildemo.com'),('tempmailer.com'),('tempmailer.de'),('tempomail.fr'),('temporarily.de'),('temporarioemail.com.br'),('temporaryemail.net'),('temporaryemail.us'),('temporaryforwarding.com'),('temporaryinbox.com'),('temporarymailaddress.com'),('tempsky.com'),('tempthe.net'),('tempymail.com'),('thanksnospam.info'),('thankyou2010.com'),('thc.st'),('thecloudindex.com'),('thelimestones.com'),('thisisnotmyrealemail.com'),('thismail.net'),('throwawayemailaddress.com'),('tilien.com'),('tittbit.in'),('tizi.com'),('tmail.ws'),('tmailinator.com'),('toiea.com'),('toomail.biz'),('topranklist.de'),('tradermail.info'),('trash-amil.com'),('trash-mail.at'),('trash-mail.com'),('trash-mail.de'),('trash2009.com'),('trash2010.com'),('trash2011.com'),('trashdevil.com'),('trashdevil.de'),('trashemail.de'),('trashmail.at'),('trashmail.com'),('trashmail.de'),('trashmail.me'),('trashmail.net'),('trashmail.org'),('trashmail.ws'),('trashmailer.com'),('trashymail.com'),('trashymail.net'),('trbvm.com'),('trialmail.de'),('trillianpro.com'),('tryalert.com'),('turual.com'),('twinmail.de'),('twoweirdtricks.com'),('tyldd.com'),('uggsrock.com'),('umail.net'),('upliftnow.com'),('uplipht.com'),('uroid.com'),('us.af'),('username.e4ward.com'),('venompen.com'),('veryrealemail.com'),('vidchart.com'),('viditag.com'),('viewcastmedia.com'),('viewcastmedia.net'),('viewcastmedia.org'),('viralplays.com'),('vomoto.com'),('vpn.st'),('vsimcard.com'),('vubby.com'),('walala.org'),('walkmail.net'),('wasteland.rfc822.org'),('webemail.me'),('webm4il.info'),('webuser.in'),('wee.my'),('weg-werf-email.de'),('wegwerf-email-addressen.de'),('wegwerf-emails.de'),('wegwerfadresse.de'),('wegwerfemail.com'),('wegwerfemail.de'),('wegwerfmail.de'),('wegwerfmail.info'),('wegwerfmail.net'),('wegwerfmail.org'),('wetrainbayarea.com'),('wetrainbayarea.org'),('wh4f.org'),('whatiaas.com'),('whatpaas.com'),('whatsaas.com'),('whopy.com'),('whtjddn.33mail.com'),('whyspam.me'),('wilemail.com'),('willhackforfood.biz'),('willselfdestruct.com'),('winemaven.info'),('wronghead.com'),('wuzup.net'),('wuzupmail.net'),('www.e4ward.com'),('www.gishpuppy.com'),('www.mailinator.com'),('wwwnew.eu'),('x.ip6.li'),('xagloo.com'),('xemaps.com'),('xents.com'),('xmaily.com'),('xoxy.net'),('xyzfree.net'),('yapped.net'),('yeah.net'),('yep.it'),('yogamaven.com'),('yopmail.com'),('yopmail.fr'),('yopmail.net'),('yourdomain.com'),('ypmail.webarnak.fr.eu.org'),('yuurok.com'),('z1p.biz'),('za.com'),('zehnminuten.de'),('zehnminutenmail.de'),('zetmail.com'),('zippymail.info'),('zoaxe.com'),('zoemail.com'),('zoemail.net'),('zoemail.org'),('zomg.info'),('zxcv.com'),('zxcvbnm.com'),('zzz.com');



# General cleanup and removal of junk

# Unused flags for mods.
ALTER TABLE table_mod DROP COLUMN big, DROP COLUMN small;

# Since this field is going away, these accounts are permanently stuck.
DELETE FROM login WHERE validated = 0;

# These ones are corrupt, and we're about to reformat passwords anyway: Goodbye.
DELETE FROM login WHERE CHAR_LENGTH(password) != 64;

# Duplicates of old versions of tables
DROP TABLE IF EXISTS avatars_list_copy_812015;
DROP TABLE ladder_season_3_safe;

# Defunct
DROP TABLE IF EXISTS nomads_beta;
DROP TABLE IF EXISTS test;
DROP TABLE IF EXISTS test2;
DROP TABLE IF EXISTS test3;

# Not referenced from server or PHP code
DROP TABLE IF EXISTS replay_comment;
DROP TABLE IF EXISTS replay_review;
DROP TABLE IF EXISTS submitted_replays;
DROP TABLE IF EXISTS user_added_replays;
DROP TABLE IF EXISTS user_groups;

# Probably an older version of the (also now dead) validated field in the login table.
DROP TABLE IF EXISTS validate_account;

# Replaced by a session cookie (yes, really)
DROP TABLE IF EXISTS steam_link_request;

# Was write-only, and all this data is now available in the new uniqueid tables anyway
DROP TABLE IF EXISTS steam_uniqueid;

# There was a hardcoded check that would filter out "thermo" maps. Let's just insert them all
# into the blacklist table and move on with our lives.
INSERT IGNORE INTO table_map_unranked (SELECT id from table_map where NAME LIKE "%thermo%");

# We query on this every time a game completes. It's probably sensible to just keep the whole fecking
# table in memory, really.
CREATE UNIQUE INDEX mod_name_idx ON game_featuredMods (gamemod);

# This column contains 2390633 never-read zeroes in LONGBLOB form.
ALTER TABLE game_replays DROP COLUMN file;



# Make map filenames unique.

# The server already assumes this to be the case, picking the first
# record from a "SELECT .. WHERE filename LIKE %blah%" (yes, really) when doing stat updates. 
# The server also enforces uniqueness at upload-time, and installation will probably catch fire
# if two maps have the same filename.
ALTER TABLE table_map DROP INDEX filename;

# Of course, ZeP fucked this up and there are two maps that have duplicates. Prune them.
# This takes a while (2 minutes on dev), given the need to use a temporary table. It'd take longer
# than that to think of a cleverer way of doing it, sooo...
#
# Prune any game records that point to these maps (there's only a few, and there's not really a way
# to save them).CREATE TEMPORARY TABLE old_stats LIKE game_player_stats;
INSERT INTO old_stats SELECT * FROM game_player_stats;
DELETE FROM game_player_stats WHERE id IN (SELECT old_stats.id as id FROM game_stats INNER JOIN old_stats on old_stats.gameId = game_stats.id where mapId IN(954, 10));
DELETE FROM game_stats WHERE mapId IN (954, 10);
DELETE FROM table_map WHERE id in (954, 10);
DROP TABLE old_stats;

CREATE UNIQUE INDEX map_filename ON table_map (filename);



# Altered approach to map-id acquisition.

# Instead of inserting a row into game_stats for every game that is hosted and using the auto_increment value as
# the id, we now query for the auto_increment value once on startup and thereafter use an atomic counter to assign
# ids to hosted games.
# This means game id numbers are not necessarily contiguous in the game_stats table, as games that never started
# "consumed" an id without launching (and hence writing to the table). We don't care, but this requires a bit of a
# rejig.

# Delete the 441963(ish) records which had only "id" and "host" fields populated (these records aren't useful)
# This removes about 1/3 of the rows from the table.
DELETE FROM game_stats WHERE startTime IS NULL AND gameMod IS NULL and mapId IS NULL and gameName IS NULL;

# Same again for the 430221(ish) records from the split-out table.
DELETE FROM game_stats_bak WHERE startTime IS NULL AND gameMod IS NULL and mapId IS NULL and gameName IS NULL;

# Now we only write once, at game-start, the timestamp can look after itself.
# Since we always insert all the columns at once, nullity isn't a thing...
# Switching from text to VARCHAR, as there's no need to store these values outside the row (and the lookup overheads
# are unnecessary).
# It's also not really necessary to have an unsigned BIGINT for the id: 2^64 games would take much,
# much longer than the expected lifetime of the universe, methinks.
ALTER TABLE game_stats MODIFY COLUMN id int UNSIGNED NOT NULL,
                       MODIFY COLUMN startTime timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                       MODIFY COLUMN gameType enum('0','1','2','3') NOT NULL,
                       MODIFY COLUMN gameMod tinyint(3) UNSIGNED NOT NULL,
                       MODIFY COLUMN `host` mediumint(8) UNSIGNED NOT NULL,
                       MODIFY COLUMN mapId mediumint(8) UNSIGNED NOT NULL,
                       MODIFY COLUMN gameName VARCHAR(128) NOT NULL,
                       ADD COLUMN validity tinyint UNSIGNED NOT NULL;

# Update map play count with a trigger on game_stats, instead of having to do another SQL call from Python-land.
# (Now we're only inserting when a game actually starts, we can do this)
CREATE TRIGGER map_play_count AFTER INSERT ON game_stats FOR EACH ROW UPDATE table_map_features set times_played = (times_played +1) WHERE map_id = NEW.mapId;



# MUST UPDATE EVERY SCORETIME THAT IS NULL TO BE THE GAME'S START TIME FIRST
# Even in the presence of the insert-then-update pattern, this field can look after itself
# ALTER TABLE game_player_stats MODIFY COLUMN scoreTime timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;




# Add support for password salting

# Can't be not-null, because incremental rehashing.
ALTER TABLE login ADD COLUMN salt CHAR(16) AFTER password;

# Steam-checking now occurs in PHP when you try and add the account (so the steamid field is
# never set before the check is performed), sessions no longer need to live in the db, and the
# new cryptographic signup mechanism means we don't need the `validated` flag any more.
# ladderCancelled is unused in the new ladder system.
# The uniqueId field doesn't hold any information that isn't in the uniqueId table, and since we
# allow multiple accounts for each UID, this column (and associated unique index) needs to go.
# The unique_id_users table associates user ids with uniqueIDs, allowing us to verify if users are
# being naughty.
ALTER TABLE login DROP COLUMN validated,
                  DROP COLUMN session,
                  DROP COLUMN steamchecked,
                  DROP COLUMN ladderCancelled,
                  DROP COLUMN uniqueId;

# Allocate extra space for pbkdf2 metadata in password field.
ALTER TABLE login MODIFY password CHAR(77) NOT NULL;

# Email addresses can be up to 254 characters long, and highly variable length fields should be
# VARCHAR not CHAR type anyway, else you waste a ton of storage (was CHAR(64))
# For now preserving ZeP's insane case sensitivity until we figure out what to do about that...
ALTER TABLE login MODIFY email VARCHAR(254) COLLATE latin1_bin NOT NULL;


# Re-combine the game stat data (skipped for now)

#ALTER TABLE game_player_stats_bak DROP FOREIGN KEY game_player_stats_bak_ibfk_1;

# There's a bunch of games with ids duplicated between game_stats and game_stats_bak.
# 7, in fact. I don't care: let's delete them.
#DELETE FROM game_player_stats_bak WHERE gameId IN (SELECT game_stats.id FROM game_stats INNER JOIN game_stats_bak ON game_stats.id = game_stats_bak.id)
#DELETE FROM game_stats_bak WHERE id IN (SELECT game_stats.id FROM game_stats INNER JOIN game_stats_bak ON game_stats.id = game_stats_bak.id)
#DELETE FROM game_stats WHERE id IN (SELECT game_stats.id FROM game_stats INNER JOIN game_stats_bak ON game_stats.id = game_stats_bak.id)



# Change the collation of usernames and emails to be case-insensitive (skipped for now)

# OH GOD WHY DID YOU GET THE COLLATION WRONG ZEP NOW I HAVE TO DO THIS.
#ALTER TABLE global_rating DROP FOREIGN KEY IdCnst;
#ALTER TABLE avatars DROP FOREIGN KEY avatars_ibfk_1;
#ALTER TABLE featured_mods_owners DROP FOREIGN KEY featured_mods_owners_ibfk_2;
#ALTER TABLE foes DROP FOREIGN KEY foes_ibfk_1;
#ALTER TABLE foes DROP FOREIGN KEY foes_ibfk_2;
#ALTER TABLE friends DROP FOREIGN KEY userCnst;
#ALTER TABLE friends DROP FOREIGN KEY friendCnst;
#ALTER TABLE game_player_stats_bak DROP FOREIGN KEY game_player_stats_bak_ibfk_2;
#ALTER TABLE game_stats_bak DROP FOREIGN KEY game_stats_bak_ibfk_5;
#ALTER TABLE global_rating DROP FOREIGN KEY id_constraint;
#ALTER TABLE ladder1v1_rating DROP FOREIGN KEY ladder1v1_rating_ibfk_1;
#ALTER TABLE lobby_ban DROP FOREIGN KEY lobby_ban_ibfk_1;
#ALTER TABLE name_history DROP FOREIGN KEY name_history_ibfk_1;
#ALTER TABLE recoveryemails_enc DROP FOREIGN KEY recoveryemails_enc_ibfk_1;
#ALTER TABLE smurf_table DROP FOREIGN KEY smurf_table_ibfk_1;
#ALTER TABLE smurf_table DROP FOREIGN KEY smurf_table_ibfk_2;
#ALTER TABLE swiss_tournaments DROP FOREIGN KEY swiss_tournaments_ibfk_1;
#ALTER TABLE swiss_tournaments_players DROP FOREIGN KEY swiss_tournaments_players_ibfk_4;
#ALTER TABLE table_map_broken DROP FOREIGN KEY table_map_broken_ibfk_2;
#ALTER TABLE table_map_comments DROP FOREIGN KEY table_map_comments_ibfk_2;
#ALTER TABLE table_map_uploaders DROP FOREIGN KEY table_map_uploaders_ibfk_2;

# TODO: Rebuild foreign keys etc.
# For now this migration is deferred until we finish getting yelled at by the stupid duplicated
# record owners.



# UniqueID system rejig...

# Uniqueid table becomes a place to associate hashes with hardware data.
ALTER TABLE uniqueid ADD hash CHAR(32) AFTER userid, DROP COLUMN userid;
UPDATE uniqueid SET hash = MD5(CONCAT(`uuid`, `mem_SerialNumber`, `deviceID`, `manufacturer`, `name`, `processorId`, `SMBIOSBIOSVersion`, `serialNumber`, `volumeSerialNumber`));

# Discards duplicates. *cackles insanely*
ALTER IGNORE TABLE uniqueid ADD UNIQUE INDEX uid_hash_index (hash);

# Associates user-ids with hardware hashes: provides the relation between users and hardware.
CREATE TABLE unique_id_users (id mediumint(8) NOT NULL AUTO_INCREMENT PRIMARY KEY, user_id mediumint(8) unsigned NOT NULL, uniqueid_hash CHAR(32) NOT NULL);
INSERT INTO unique_id_users (user_id, uniqueid_hash) SELECT userid, MD5( CONCAT( `uuid` , `mem_SerialNumber` , `deviceID` , `manufacturer` , `name` , `processorId` , `SMBIOSBIOSVersion` , `serialNumber` , `volumeSerialNumber` ) ) FROM uniqueid;

# A table for whitelisting ids.
ALTER TABLE `uniqueid_exempt` CHANGE `idUser` `user_id` MEDIUMINT(8) UNSIGNED;

# Persist game-unrankedness-reasons to the database

# Maps reason-ids to descriptive strings (join with for generating pretty reports)
CREATE TABLE invalid_game_reasons (id TINYINT NOT NULL AUTO_INCREMENT, message VARCHAR(100) NOT NULL, PRIMARY KEY(id));

# Populate it
INSERT INTO `invalid_game_reasons` VALUES (1,'Too many desyncs'),(2,'Only assassination mode is ranked'),(3,'Fog of war was disabled'),(4,'Cheats were enabled'),(5,'Prebuilt units were enabled'),(6,'No rush was enabled'),(7,'Unacceptable unit restrictions were enabled'),(8,'An unacceptable map was used'),(9,'Game was too short (probably had a technical fault early on)'),(10,'An unacceptable mod was used');
INSERT INTO invalid_game_reasons(message) VALUES("Coop is not ranked");

# Records in game_stats_bak (the stupid split table madness ZeP did) just have a flag, so when we re-combine we'll need this:
INSERT INTO invalid_game_reasons(message) VALUES("Reason not known");

# EndTime of game_stats is redundant: can be inferred from game_player_stats
ALTER TABLE game_stats DROP COLUMN EndTime;


# No more ladder map selection.
DROP TABLE ladder_map_selection;


# Featured mods that do not have an associated files or updates table cannot exist (all of these
# rows seem to be fluff anyway, so let's just munch them)
DELETE FROM game_featuredMods WHERE gamemod IN ("custom", "nftw", "aprilfools");

# It is unclear why this was not set before...
UPDATE game_featuredMods SET publish = 1 where gamemod = "faf";



# Merge friends and foes tables so "friend and foe" cannot be a thing anymore...

# Turn everyone who is both a friend and a foe of someone into just a foe.
DELETE FROM friends WHERE idFriend IN (SELECT * FROM (SELECT friends.idFriend FROM friends INNER JOIN foes ON friends.idUser = foes.idUser WHERE friends.idFriend = foes.idFoe) AS TOASTER);

# The new table to hold friends/foes
CREATE TABLE friends_and_foes (
  user_id MEDIUMINT UNSIGNED NOT NULL,
  subject_id MEDIUMINT UNSIGNED NOT NULL,
  status ENUM("FRIEND", "FOE"),
  PRIMARY KEY(user_id, subject_id)
);

# Copy the old friends and foes data over (safe because we know the pairings are unique now)
INSERT INTO friends_and_foes(user_id, subject_id, status) SELECT foes.idUser, foes.idFoe, "FOE" AS status FROM foes;
INSERT INTO friends_and_foes(user_id, subject_id, status) SELECT friends.idUser, friends.idfriend, "FRIEND" AS status FROM friends;

DROP TABLE friends;
DROP TABLE foes;



# Don't name tables after SQL queries
ALTER TABLE ladder_division CHANGE COLUMN `limit` `threshold` int unsigned NOT NULL;


# Optimise all the tables we restructured (so we might recover space or be less fragmented or such)
OPTIMIZE TABLE login;
OPTIMIZE TABLE table_mod;
